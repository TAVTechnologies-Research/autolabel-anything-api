import os
import time
import pathlib
import asyncio
import cv2 as cv
import subprocess
from typing import List, Union, Tuple, Optional
from fastapi import Depends

import schemas
import database_models as dbmodels

from db import get_db
from enums import VideoStatusEnum as VideoStatus


def get_ffmpeg_command(
    video_path: str, frames_path: str, digit_count: int = 8
) -> List[str]:
    """Return ffmpeg command to extract frames from video.

    Args:
        video_path (str): src video path
        frames_path (str): dst frames path
        digit_count (int, optional): %0{count}d.jpg Defaults to 8.

    Returns:
        List[str]: command to run with subprocess.run
    """
    return [
        "ffmpeg",
        "-i",
        video_path,
        os.path.join(frames_path, f"%0{digit_count}d.jpg"),
    ]


# FIXME: Fix the type hinting for this function
def extract_frames(
    video_id: int,
) -> None:
    """
    Extract frames from video and store them to defined folder.
    Updates database job_status.

    Args:
        video_id (int): video_id from database
    """
    db = next(get_db())
    # get the video from database
    video: dbmodels.Video = (
        db.query(dbmodels.Video).filter_by(video_id=video_id).first()
    )
    if not video:
        return

    if video.status != VideoStatus.PENDING.value:
        return

    extract_frame_path = video.frames_path

    try:
        process = subprocess.Popen(
            get_ffmpeg_command(video.video_path, extract_frame_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        while process.poll() is None:
            if video.status == VideoStatus.PENDING.value:
                video.status = VideoStatus.PROCESSING.value
                db.commit()
                db.refresh(video)
            time.sleep(0.25)

        if process.returncode == 0:
            video.status = VideoStatus.READY.value
        else:
            video.status = VideoStatus.FAILED.value
    except Exception as e:
        video.status = VideoStatus.FAILED.value
    finally:
        db.commit()
        db.refresh(video)


async def convert_video_to_mp4(
    src_video_path: Union[str, pathlib.Path],
    dst_video_path: Union[str, pathlib.Path],
    inc_audio: bool = False,
    target_fps: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Converts a video to .mp4 format using ffmpeg.

    :param src_video_path: (Union[str, pathlib.Path]): Source video path.
    :param dst_video_path: (Union[str, pathlib.Path]): Destination video path.
    :param inc_audio:param (bool, optional): Include audio in the output video. Defaults to False.
    """

    def get_ffmpeg_command(inc_audio: bool) -> List[Union[str, pathlib.Path]]:
        # if inc_audio:
        #    return [
        #        "/usr/bin/ffmpeg",
        #        "-i",
        #        src_video_path,
        #        "-c:v",
        #        "libx264",
        #        "-c:a",
        #        "aac",
        #        "-strict",
        #        "experimental",
        #        "-b:a",
        #        "192k",
        #        dst_video_path,
        #    ]
        # return [
        #    "/usr/bin/ffmpeg",
        #    "-i",
        #    src_video_path,
        #    "-c:v",
        #    "libx264",
        #    "-an",
        #    dst_video_path,
        # ]
        command = [
            "/usr/bin/ffmpeg",
            "-i",
            src_video_path,
            "-c:v",
            "libx264",
        ]
        if target_fps:
            command.extend(["-r", str(target_fps)])

        if inc_audio:
            command.extend(["-c:a", "aac", "-strict", "experimental", "-b:a", "192k"])
        else:
            command.append("-an")

        command.append(dst_video_path)
        return command

    command = get_ffmpeg_command(inc_audio)

    # try:
    # process = subprocess.Popen(
    #    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    # )
    # while process.poll() is None:
    #    time.sleep(0.25)
    #
    # if process.returncode == 0:
    #    return (True, None)
    # else:
    #    return False, "An error occurred while converting video to mp4."
    #

    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # Wait for the process to complete
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            return True, stdout.decode("utf-8").strip()
        else:
            error_message = stderr.decode("utf-8").strip()
            return False, f"An error occurred: {error_message}"

    except Exception as e:
        return False, str(e)
    # except Exception as e:
    #    return False, str(e)
