from pydantic import BaseModel, field_validator, model_validator
from typing import List, Union, Tuple, Any, Optional
from typing_extensions import Self

import numpy as np


class PointPrompt(BaseModel):
    id: str
    frameNumber: int
    x: float
    y: float
    markerType: int

    @field_validator("markerType", mode="after")
    @classmethod
    def _validate_marker_tye(cls, v):
        if isinstance(v, int):
            if v not in [0, 1]:
                raise ValueError("Marker type should be 0 or 1")
        return v

    # x and y should be between 0 and 1
    @field_validator("x", mode="after")
    @classmethod
    def _validate_x(cls, v):
        if isinstance(v, float):
            if v <= 0 or v >= 1:
                raise ValueError("x should be between 0 and 1")
        return v

    @field_validator("y", mode="after")
    @classmethod
    def _validate_y(cls, v):
        if isinstance(v, float):
            if v <= 0 or v >= 1:
                raise ValueError("y should be between 0 and 1")
        return v

    class Config:
        from_attributes = True


class AnnotationObject(BaseModel):
    id: str
    label: Optional[str] = None
    objectColor: Any  # FIXME: Validate objectColor to be a valid color in rgb format
    child: List[PointPrompt]

    @field_validator("child", mode="after")
    @classmethod
    def _validate_child(cls, v):
        if isinstance(v, list):
            if len(v) == 0:
                raise ValueError("Child should not be empty")
            for child in v:
                if not isinstance(child, PointPrompt):
                    raise ValueError("Child should be a PointPrompt object")
        return v


class SingleFrameAnnotationObject(AnnotationObject):
    # each objects must be on the same frame
    @field_validator("child", mode="after")
    @classmethod
    def _validate_frame(cls, v):
        frame_numbers = set()
        for child in v:
            frame_numbers.add(child.frameNumber)
        if len(frame_numbers) > 1:
            raise ValueError("All child objects should be on the same frame")
        return v
