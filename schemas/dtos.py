from __future__ import annotations
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, TypeVar

from .prompt import PointPrompt, AnnotationObject, SingleFrameAnnotationObject
from .intercom import InitModelIntercom, Intercom


class ResponseCoverBase(BaseModel):
    data: Any
    error: Any = None
    meta: Any = None
    message: Optional[str] = None


class ResponseCover(BaseModel):
    msg_type: str
    data: Any = None
    error: Any = None
    meta: Any = None
    message: Optional[str] = None

    class Config:
        from_attributes = True


class ResetTaskInputCover(ResponseCover):
    msg_type: str = "reset"


class ErrorResponseCover(ResponseCover):
    msg_type: str = "error"
    data: None = None
    error: Dict[str, Any] = dict()
    meta: Any = None
    message: str = "An error occurred"

    class Config:
        from_attributes = True


class PointPromptInputCover(ResponseCover):
    msg_type: str = "add_points"
    data: List[AnnotationObject] = []

    class Config:
        from_attributes = True


class SingleFramePointPromptInputCover(PointPromptInputCover):
    data: List[SingleFrameAnnotationObject] = []


class RunInferenceInputCover(PointPromptInputCover):
    msg_type: str = "run_inference"

    class Config:
        from_attributes = True


class RemoveObjectInputCover(ResponseCover):
    msg_type: str = "remove_object"
    data: List[str] = []  # list of object ids

    class Config:
        from_attributes = True


class InitilizeModelInputCover(ResponseCover):
    msg_type: str = "initialize_model"
    data: InitModelIntercom

    class Config:
        from_attributes = True


class InitilizeModelResponseCover(ResponseCover):
    msg_type: str = "initialize_model"
    data: Optional[Intercom] = None

    class Config:
        from_attributes = True


ResponseType = TypeVar("ResponseType", bound=ResponseCover)
