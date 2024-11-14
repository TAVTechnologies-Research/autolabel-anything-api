import os
import json
from datetime import datetime
from re import S

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy import event, insert, update
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.orm import relationship, backref

from db_base import Base


class Annotation(Base):
    __tablename__ = "annotation"
    annotation_id = Column(Integer, primary_key=True, nullable=False)
    task_id = Column(Integer, ForeignKey("task.task_id"))

    image_id = Column(String, nullable=False)
    image_path = Column(String, nullable=False)
    annotation_data = Column(String, nullable=True, server_default=text("'{}'"))
    annotation_type = Column(String, nullable=False)
    frame_idx = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    annotated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
