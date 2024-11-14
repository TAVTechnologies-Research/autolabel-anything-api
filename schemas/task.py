from pydantic import BaseModel
from typing import List, Optional
from enums import TaskStatusEnum
from datetime import datetime

from .dtos import ResponseCover


class TaskStatus(BaseModel):
    status: TaskStatusEnum

    class Config:
        from_attributes = True


class TaskStatusResponseCover(ResponseCover):
    msg_type: None = None
    data: TaskStatus  # type: ignore
    message: Optional[str] = None

    class Config:
        from_attributes = True


class TaskOut(BaseModel):
    task_id: int
    task_uuid: str
    task_name: str
    created_at: datetime
    video_id: int
    ai_model_id: int
    is_active: bool
    last_interaction: datetime

    class Config:
        from_attributes = True


class TaskInformationOutputCover(ResponseCover):
    msg_type: None = None
    data: TaskOut  # type: ignore
    message: Optional[str] = None

    class Config:
        from_attributes = True
