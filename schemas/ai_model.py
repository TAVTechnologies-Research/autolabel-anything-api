from typing import Optional
from pydantic import BaseModel, Field
from .video import VideoOutDetailed
from enums import TaskStatusEnum


class AiModel(BaseModel):
    ai_model_id: int  # = Field(alias="model_id")
    ai_model_name: str  # = Field(alias="model_name")
    checkpoint_path: str
    config_path: str

    class Config:
        from_attributes = True
        populated_by_name = True


class InitModelRequest(BaseModel):
    ai_model_id: int  # = Field(alias="model_id")
    video_id: int
    task_name: str = ""

    class Config:
        from_attributes = True
