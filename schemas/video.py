from datetime import datetime
from pydantic import BaseModel
from enums import VideoStatusEnum

from typing import Optional, Dict, Any


class VideoIn(BaseModel):
    video_name: str
    video_path: str
    target_fps: Optional[int] = None

    class Config:
        from_attributes = True


class VideoOut(BaseModel):
    video_id: int
    video_name: str
    status: str
    created_at: datetime
    file_size: int  # in bytes
    thumbnail: Optional[Dict[str, Any]] = None # base64 encoded image of video thumbnail

    class Config:
        from_attributes = True


class VideoOutDetailed(VideoOut):
    video_height: int
    video_width: int
    video_duration: int
    video_path: str
    frames_path: str
    video_fps: int
    frame_count: Optional[int] = None

    class Config:
        from_attributes = True


class VideoInformation(BaseModel):
    video_width: int
    video_height: int
    video_duration: int
    video_fps: float
    frame_count: int

    class Config:
        from_attributes = True


class VideoStatus(BaseModel):
    status: VideoStatusEnum

    class Config:
        from_attributes = True
