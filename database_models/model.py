import os
from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy import event, insert, update
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.orm import relationship, backref

from db_base import Base
from settings import settings


class AiModel(Base):
    __tablename__ = "ai_model"
    ai_model_id = Column(Integer, primary_key=True, nullable=False)
    ai_model_name = Column(String, nullable=True, unique=True)
    checkpoint_path = Column(String, nullable=False)
    config_path = Column(String, nullable=False)


DEFAULT_MODELS = [
    {
        "model_name": "Hiera Base Plus",
        "checkpoint_path": os.path.join(
            settings.MODEL_CHECKPOINT_DIRECTORY, "sam2_hiera_base_plus.pt"
        ),
        "config_path": "sam2_hiera_b+.yaml",
    },
    {
        "model_name": "Hiera Large",
        "checkpoint_path": os.path.join(
            settings.MODEL_CHECKPOINT_DIRECTORY, "sam2_hiera_large.pt"
        ),
        "config_path": "sam2_hiera_l.yaml",
    },
    {
        "model_name": "Hiera Small",
        "checkpoint_path": os.path.join(
            settings.MODEL_CHECKPOINT_DIRECTORY, "sam2_hiera_small.pt"
        ),
        "config_path": "sam2_hiera_s.yaml",
    },
    {
        "model_name": "Hiera Tiny",
        "checkpoint_path": os.path.join(
            settings.MODEL_CHECKPOINT_DIRECTORY, "sam2_hiera_tiny.pt"
        ),
        "config_path": "sam2_hiera_t.yaml",
    },
]


@event.listens_for(AiModel.__table__, "after_create")
def insert_initial_values(target, connection, **kwargs):
    connection.execute(AiModel.__table__.insert(), DEFAULT_MODELS)
