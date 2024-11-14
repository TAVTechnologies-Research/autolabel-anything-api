import os
import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy import event, insert, update
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.orm import relationship, backref

from db_base import Base


class Task(Base):
    __tablename__ = "task"
    task_id = Column(Integer, primary_key=True, nullable=False)
    task_uuid = Column(String, nullable=False, unique=True)
    task_name = Column(String, nullable=True, unique=False, server_default=text("''"))

    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    video_id = Column(Integer, ForeignKey("video.video_id"))
    ai_model_id = Column(Integer, ForeignKey("ai_model.ai_model_id"))
    task_config = Column(
        String, nullable=True, server_default=text("'{}'")
    )
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    last_interaction = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    exported_at = Column(
        TIMESTAMP(timezone=True), nullable=True, server_default=text("null")
    )
    description = Column(String, nullable=True)

