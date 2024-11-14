import os
import pathlib
import cv2 as cv

from typing import Union

import schemas


def get_video_information(
    video_path: Union[str, pathlib.Path]
) -> schemas.VideoInformation:
    if isinstance(video_path, str):
        video_path = pathlib.Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video path does not exist: {video_path}")
    video = cv.VideoCapture(str(video_path))
    video_width = int(video.get(cv.CAP_PROP_FRAME_WIDTH))
    video_height = int(video.get(cv.CAP_PROP_FRAME_HEIGHT))
    video_fps = float(video.get(cv.CAP_PROP_FPS))
    frame_count = int(video.get(cv.CAP_PROP_FRAME_COUNT))
    video_duration = (frame_count / video_fps) * 1000  # ms
    video.release()
    return schemas.VideoInformation(
        video_width=video_width,
        video_height=video_height,
        video_duration=int(video_duration),
        video_fps=video_fps,
        frame_count=frame_count,
    )


def get_frame_count_by_duration(duration: int, fps: float) -> int:
    """Calculates number of frames based on duration and fps

    Args:
        duration (int): duration in milliseconds
        fps (float): frames per seconds

    Returns:
        int: number of frames
    """
    return int((duration / 1000) * fps)
