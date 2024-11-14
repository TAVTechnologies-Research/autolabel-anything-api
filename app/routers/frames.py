import os
import uuid
import base64
import shutil
import asyncio
import aiofiles
from io import BytesIO
from typing import List, Dict, Optional, Union
from datetime import datetime
from PIL import Image

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    Header,
    Response,
)
from fastapi.responses import JSONResponse, StreamingResponse

from db.redis_client import get_redis_client
import schemas
import database_models as dbmodels
from db import get_db
from utils import get_video_information, get_frame_count_by_duration
from settings import settings
from enums import VideoStatusEnum


router = APIRouter(prefix="/frames", tags=["frames"])


@router.get(
    "/{video_id}/frame/{frame_number}",
    status_code=status.HTTP_200_OK,
)
async def get_frame_by_number(
    video_id: str,
    frame_number: int,
    scale: float = 1,
    db=Depends(get_db),
) -> Response:
    video: Optional[dbmodels.Video] = (
        db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    )
    # check if video exists
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # TODO: total frame count migrated to be in the db -> use that instead (after fulll migration)
    total_frame_count = get_frame_count_by_duration(
        duration=video.video_duration, fps=video.video_fps  # type: ignore
    )
    # check if frame number is out of range
    if frame_number < 0 or frame_number >= total_frame_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Frame number is out of range",
        )

    frame_path = os.path.join(
        str(video.frames_path), f"{str(frame_number+1).zfill(8)}.jpg"
    )
    if not os.path.exists(frame_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frame not found",
        )

    image = Image.open(frame_path)
    # if scale is not 1, resize the image send with temporary file
    if scale != 1:
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size)
        # Save the image to a BytesIO buffer in JPEG format to retain compression
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        image_in_bytes = buffer.getvalue()
    else:
        with open(frame_path, "rb") as file:
            image_in_bytes = file.read()

    headers = {
        "Requested-Frame-Number": str(frame_number),
        "Total-Frames": str(total_frame_count),
        "Frame-Scale": str(scale),
        "Image-Widht": str(image.width),
        "Image-Height": str(image.height),
    }

    # return jpg image
    return Response(content=image_in_bytes, media_type="image/jpeg", headers=headers)


async def process_image(frame_path: str, scale: float) -> Dict[str, Union[str, int]]:
    async with aiofiles.open(frame_path, "rb") as file:
        image_in_bytes = await file.read()

    loop = asyncio.get_event_loop()
    image = await loop.run_in_executor(None, Image.open, BytesIO(image_in_bytes))

    if scale != 1:
        new_size = (int(image.width * scale), int(image.height * scale))
        image = await loop.run_in_executor(None, image.resize, new_size)
        buffer = BytesIO()
        await loop.run_in_executor(None, image.save, buffer, "JPEG")
        image_in_bytes = buffer.getvalue()

    image_base64 = base64.b64encode(image_in_bytes).decode("utf-8")

    return {
        "image_base64": image_base64,
        "width": image.width,
        "height": image.height,
    }


async def process_image_webp(
    frame_path: str, scale: float
) -> Dict[str, Union[bytes, int]]:
    async with aiofiles.open(frame_path, "rb") as file:
        image_in_bytes = await file.read()

    loop = asyncio.get_event_loop()
    image = await loop.run_in_executor(None, Image.open, BytesIO(image_in_bytes))

    if scale != 1:
        new_size = (int(image.width * scale), int(image.height * scale))
        image = await loop.run_in_executor(None, image.resize, new_size)

    buffer = BytesIO()
    await loop.run_in_executor(None, image.save, buffer, "WEBP")  # Save as WebP
    image_in_bytes = buffer.getvalue()

    return {
        "image_bytes": image_in_bytes,  # Return raw image bytes
        "width": image.width,
        "height": image.height,
    }


# TODO: Cache must be stored with all request parameters
@router.get(
    "/{video_id}",
    status_code=status.HTTP_200_OK,
)
async def get_all_frames(
    video_id: int,
    scale: float = 1.0,
    start_frame: int = 0,
    end_frame: Optional[int] = None,
    thumbnail: bool = False,
    db=Depends(get_db),
    rcli=Depends(get_redis_client),
) -> Response:
    video: Optional[dbmodels.Video] = (
        db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    )
    # check if video exists
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    if video.frame_count is not None:
        total_frame_count = int(video.frame_count)  # type: ignore
    else:
        total_frame_count = get_frame_count_by_duration(
            duration=video.video_duration, fps=video.video_fps  # type: ignore
        )

    if start_frame < 0 or start_frame > total_frame_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start frame number is out of range",
        )
    if end_frame is None:
        end_frame = total_frame_count - 1
    elif end_frame >= total_frame_count:
        end_frame = total_frame_count - 1

    if end_frame < start_frame:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End frame number is less than start frame number",
        )

    print("Checking cache")
    is_cached = rcli.get_json(f"frames:{video_id}:{start_frame}:{end_frame}:{scale}")

    thumbnail_image = None
    if thumbnail:  # FIXME: thumbnail is not caching
        thumbnail_image = await process_image(
            frame_path=os.path.join(
                str(video.frames_path), f"{str(start_frame+1).zfill(8)}.jpg"
            ),
            scale=0.1,
        )

    if is_cached:
        print("Returned from cache")
        is_cached["thumbnail"] = thumbnail_image
        return JSONResponse(
            content=is_cached,
            headers={
                "Total-Frames": str(total_frame_count),
                "Start-Frame": str(start_frame),
                "End-Frame": str(end_frame),
                "Frame-Scale": str(scale),
            },
        )
    print("Not cached")
    frames: List[Dict[str, Union[str, int]]] = []
    tasks = []
    for frame_number in range(start_frame, int(end_frame) + 1):
        frame_path = os.path.join(
            str(video.frames_path), f"{str(frame_number+1).zfill(8)}.jpg"
        )

        if not os.path.exists(frame_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Frame not found at frame number: {frame_number}",
            )

        tasks.append(process_image(frame_path, scale))

    frames_data = await asyncio.gather(*tasks)

    for frame_number, frame_data in enumerate(frames_data, start=start_frame):
        frames.append(
            {
                "frame_number": frame_number,
                "image_base64": frame_data["image_base64"],
            }
        )

    if not is_cached:
        print("Adding to cache")
        rcli.add_json(
            f"frames:{video_id}:{start_frame}:{end_frame}:{scale}",
            {
                "frames": frames,
                "width": frames_data[0]["width"],
                "height": frames_data[0]["height"],
            },
            ttl=60 * 20,
        )

    return JSONResponse(
        content={
            "frames": frames,
            "width": frames_data[0]["width"],
            "height": frames_data[0]["height"],
            "thumbnail": thumbnail_image,
        },
        headers={
            "Total-Frames": str(total_frame_count),
            "Start-Frame": str(start_frame),
            "End-Frame": str(end_frame),
            "Frame-Scale": str(scale),
        },
    )


#@router.get(
#    "/webp/{video_id}",
#    status_code=status.HTTP_200_OK,
#)
#async def get_all_frames_webp(
#    video_id: int,
#    scale: float = 1.0,
#    start_frame: int = 0,
#    end_frame: Optional[int] = None,
#    db=Depends(get_db),
#) -> Response:
#    video: Optional[dbmodels.Video] = (
#        db.query(dbmodels.Video).filter_by(video_id=video_id).first()
#    )
#    # check if video exists
#    if not video:
#        raise HTTPException(
#            status_code=status.HTTP_404_NOT_FOUND,
#            detail="Video not found",
#        )
#
#    if video.frame_count is not None:
#        total_frame_count = video.frame_count
#    else:
#        total_frame_count = get_frame_count_by_duration(
#            duration=video.video_duration, fps=video.video_fps  # type: ignore
#        )
#
#    if start_frame < 0 or start_frame > total_frame_count:  # type: ignore
#        raise HTTPException(
#            status_code=status.HTTP_400_BAD_REQUEST,
#            detail="Start frame number is out of range",
#        )
#    if end_frame is None:
#        end_frame = total_frame_count - 1  # type: ignore
#    elif end_frame >= total_frame_count:  # type: ignore
#        end_frame = total_frame_count - 1  # type: ignore
#
#    if end_frame < start_frame: # type: ignore
#        raise HTTPException(
#            status_code=status.HTTP_400_BAD_REQUEST,
#            detail="End frame number is less than start frame number",
#        )
#
#    frames = []
#    tasks = []
#    for frame_number in range(start_frame, end_frame + 1):  # type: ignore
#        frame_path = os.path.join(
#            str(video.frames_path), f"{str(frame_number + 1).zfill(8)}.jpg"
#        )
#
#        if not os.path.exists(frame_path):
#            raise HTTPException(
#                status_code=status.HTTP_404_NOT_FOUND,
#                detail=f"Frame not found at frame number: {frame_number}",
#            )
#
#        tasks.append(process_image(frame_path, scale))
#
#    frames_data = await asyncio.gather(*tasks)
#
#    boundary = "frame_boundary"
#    parts = []
#
#    for frame_number, frame_data in enumerate(frames_data, start=start_frame):
#        frame_bytes = frame_data["image_bytes"]
#        part_headers = {
#            "Content-Type": "image/webp",
#            "Content-Disposition": f'attachment; filename="frame_{frame_number}.webp"',
#        }
#        parts.append((frame_bytes, part_headers))
#
#    response_headers = {
#        "Total-Frames": str(total_frame_count),
#        "Start-Frame": str(start_frame),
#        "End-Frame": str(end_frame),
#        "Frame-Scale": str(scale),
#    }
#
#    return MultipartResponse(parts, headers=response_headers, boundary=boundary)
