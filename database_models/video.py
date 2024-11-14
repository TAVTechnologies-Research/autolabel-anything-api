import os
from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Float
from sqlalchemy import event, insert, update
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.orm import relationship, backref

from db_base import Base


class Video(Base):
    __tablename__ = "video"
    video_id = Column(Integer, primary_key=True, nullable=False)
    video_name = Column(String, nullable=False, unique=True)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    video_width = Column(Integer, nullable=False)
    video_height = Column(Integer, nullable=False)
    video_duration = Column(Integer, nullable=False)
    video_path = Column(String, nullable=False)
    video_fps = Column(Float, nullable=False)
    frame_count = Column(Integer, nullable=True)

    frames_path = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    status = Column(String, nullable=False, server_default="pending")

    is_active = Column(Boolean, nullable=False, server_default="true")
