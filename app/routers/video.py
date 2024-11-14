import os
import uuid
import shutil
import pathlib
import asyncio
from typing import List, Dict, Optional, Union
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from fastapi.responses import StreamingResponse

import schemas
import database_models as dbmodels
from db import get_db
from utils import get_video_information
from settings import settings
from enums import VideoStatusEnum
from background_tasks import extract_frames, convert_video_to_mp4

from .frames import process_image

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}

router = APIRouter(prefix="/videos", tags=["videos"])


# FIXME: If any error occur before the process finishes, raw_video should be removed
#   since it cannot be tracked later.
@router.post(
    "/add", response_model=schemas.VideoOut, status_code=status.HTTP_202_ACCEPTED
)
async def add_video(
    video: schemas.VideoIn, background_tasks: BackgroundTasks, db=Depends(get_db)
) -> schemas.VideoOut:
    # check video exists by name
    video_exists = (
        db.query(dbmodels.Video).filter_by(video_name=video.video_name).first()
    )
    if video_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video with this name already exists",
        )

    # check video path is exists
    if not os.path.exists(video.video_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video path does not exist",
        )

    # check mp4
    # if not video.video_path.endswith(".mp4"):
    #    raise HTTPException(
    #        status_code=status.HTTP_400_BAD_REQUEST,
    #        detail="Video file must be in mp4 format",
    #    )

    # check video extension is one of the allowed extensions
    if not video.video_path.split(".")[-1] in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video file must be in mp4, avi, mov or mkv format",
        )

    video_uuid = str(uuid.uuid4())
    internal_video_path = os.path.join(
        settings.RAW_VIDEO_DIRECTORY, f"{video_uuid}.mp4"
    )

    # convert video to mp4
    target_fps = video.target_fps if video.target_fps else None
    conversion_success, error_msg = await convert_video_to_mp4(
        video.video_path, internal_video_path, inc_audio=False, target_fps=target_fps
    )

    if not conversion_success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to convert video to mp4.\n{error_msg}",
        )

    # get video information
    try:
        video_information = get_video_information(internal_video_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    internal_video_frames_path = os.path.join(
        settings.EXTRACTED_FRAMES_DIRECTORY, video_uuid
    )
    os.makedirs(internal_video_frames_path, exist_ok=True)
    # shutil.copyfile(video.video_path, internal_video_path)

    try:
        new_video = dbmodels.Video(
            video_name=video.video_name,
            video_width=video_information.video_width,
            video_height=video_information.video_height,
            video_path=internal_video_path,
            frames_path=internal_video_frames_path,
            video_fps=video_information.video_fps,
            video_duration=video_information.video_duration,
            file_size=os.path.getsize(internal_video_path),
            frame_count=video_information.frame_count,
        )
        db.add(new_video)
        db.commit()
        db.refresh(new_video)

        # add background task to extract frames
        background_tasks.add_task(extract_frames, video_id=new_video.video_id)  # type: ignore
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error\n{str(e)}",
        )
    finally:
        # db.close()
        ...
    return new_video


@router.get(
    "/",
    response_model=List[schemas.VideoOut],
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def get_videos(
    thumbnail: bool = False, db=Depends(get_db)
) -> List[schemas.VideoOut]:
    """Returns list of all videos

    Args:
        thumbnail (bool, optional): Get thumbnail with video information. Defaults to False.
        db (_type_, optional): DB Session. Defaults to Depends(get_db).

    Returns:
        List[Optional[schemas.VideoOut]]: _description_
    """
    videos = db.query(dbmodels.Video).all()
    videos = [schemas.VideoOut.model_validate(video) for video in videos]
    if thumbnail:
        for video in videos:
            # get video detail by video_id
            detail = await get_video(video.video_id, db=db)
            thumbnail_image = await process_image(
                frame_path=str(
                    os.path.join(detail.frames_path, f"{str(1).zfill((8))}.jpg")
                ),
                scale=0.2,
            )
            video.thumbnail = thumbnail_image

    return videos


@router.get(
    "/{video_id}",
    response_model=schemas.VideoOutDetailed,
    status_code=status.HTTP_200_OK,
)
async def get_video(video_id: int, db=Depends(get_db)) -> schemas.VideoOutDetailed:
    # check if video exists
    video = db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )
    number_of_frames = len(os.listdir(video.frames_path))
    return video


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_video(video_id: int, db=Depends(get_db)):
    # check if video exists
    video = db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )
    # check if video is processing
    # FIXME: If stuck at pending, user will not be able to delete the video
    #   find a way to cancel the pending background task
    if (
        video.status == VideoStatusEnum.PROCESSING.value
        or video.status == VideoStatusEnum.PENDING.value
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video is processing. Please wait until processing is complete",
        )

    # remove raw_video
    if os.path.exists(video.video_path):
        os.remove(video.video_path)

    # remove extracted frames
    if os.path.exists(video.frames_path):
        shutil.rmtree(video.frames_path)

    # delete video
    db.delete(video)
    db.commit()
    db.close()
    return


@router.get(
    "/status/{video_id}",
    response_model=schemas.VideoStatus,
    status_code=status.HTTP_200_OK,
)
async def get_video_status(video_id: int, db=Depends(get_db)) -> schemas.VideoStatus:
    # check if video exists
    video = db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    return schemas.VideoStatus(status=video.status)


@router.get(
    "/stream/{video_id}",
    status_code=status.HTTP_200_OK,
)
async def stream_video(
    video_id: int,
    db=Depends(get_db),
    package_size: int = Header(1),
) -> StreamingResponse:
    # check if video exists
    video: Optional[dbmodels.Video] = (
        db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    )
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )
    # check if video path exists
    if not os.path.exists(video.video_path):  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Video path does not exists. Please re-upload the video",
        )

    # check the video status
    if not video.status == VideoStatusEnum.READY.value:  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video is not processed yet",
        )

    def iterfile():
        with open(video.video_path, "rb") as file:  # type: ignore
            print(
                f"Requested video size: {os.path.getsize(video.video_path)/ 1024 / 1024:.2f} MB with package size: {package_size} MB"  # type: ignore
            )

            while chunk := file.read(
                package_size * 1024 * 1024
            ):  # Read the file in chunks of 1 MB
                # print("ok -> ", len(chunk) ,"->", package_size_in_mb * 1024 * 1024)
                yield chunk

    response = StreamingResponse(
        iterfile(),
        media_type="video/mp4",
    )
    response.headers["X-Stream"] = "true"
    return response


@router.get("/stream-partial/{video_id}", status_code=status.HTTP_206_PARTIAL_CONTENT)
def stream_video_partial(
    video_id: int, db=Depends(get_db), range_header: str = Header(None, alias="range")
):
    video: Optional[dbmodels.Video] = (
        db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    )
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    # check if video path exists
    if not os.path.exists(video.video_path):  # type: ignore
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Video path does not exists. Communicate with administrator.",
        )

    file_size_in_bytes = os.path.getsize(video.video_path)  # type: ignore

    try:
        # Parse the range header
        range_str = range_header.replace("bytes=", "")
        range_start, range_end = range_str.split("-")

        # Convert to integers, handle the case of range_end being empty
        range_start = int(range_start)
        range_end = int(range_end) if range_end else file_size_in_bytes - 1
        chunk_size = range_end - range_start + 1
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid range header",
        )

    if range_start >= file_size_in_bytes or range_end >= file_size_in_bytes:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Requested range is not satisfiable",
        )

    def iterfile():
        with open(video.video_path, "rb") as video_file:  # type: ignore
            video_file.seek(range_start)
            yield video_file.read(chunk_size)

    # create response headers
    headers = {
        "Content-Range": str(f"bytes {range_start}-{range_end}/{file_size_in_bytes}"),
        "Accept-Ranges": str("bytes"),
        "Content-Length": str(chunk_size),
        "Content-Type": "video/mp4",
    }
    print(headers)
    # return range for test
    response = StreamingResponse(
        iterfile(),
        headers=headers,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="video/mp4",
    )
    response.headers["X-Stream"] = "true"
    return response
