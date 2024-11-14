from pydantic import BaseModel

from typing import Literal, Union, List

from .prompt import AnnotationObject

from .ai_model import AiModel
from .video import VideoOutDetailed


class InitModelIntercom(BaseModel):
    ai_model: AiModel
    video: VideoOutDetailed

    class Config:
        from_attributes = True


class AddPointIntercom(BaseModel):
    data: List[AnnotationObject]

    class Config:
        from_attributes = True


class Intercom(BaseModel):
    task_type: Literal["initialize_model", "add_points", "terminate_model", "reset"]
    task: Union[InitModelIntercom, AddPointIntercom, None]
    uuid: str

    class Config:
        from_attributes = True
