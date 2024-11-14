import os

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_HOSTNAME: str = str(
        os.environ.get("DATABASE_HOSTNAME")
    )  # Field(None, env='DATABASE_HOST')
    DATABASE_PORT: str = str(os.environ.get("DATABASE_PORT"))
    DATABASE_NAME: str = str(os.environ.get("DATABASE_NAME"))
    DATABASE_USERNAME: str = str(os.environ.get("DATABASE_USERNAME"))
    DATABASE_PASSWORD: str = str(os.environ.get("DATABASE_PASSWORD"))

    RABBITMQ_HOSTNAME: str = str(os.environ.get("RABBITMQ_HOSTNAME"))
    RABBITMQ_PORT: str = str(os.environ.get("RABBITMQ_PORT"))
    RABBITMQ_USERNAME: str = str(os.environ.get("RABBITMQ_USERNAME"))
    RABBITMQ_PASSWORD: str = str(os.environ.get("RABBITMQ_PASSWORD"))
    RABBITMQ_VHOST: str = str(os.environ.get("RABBITMQ_VHOST"))

    REDIS_HOSTNAME: str = str(os.environ.get("REDIS_HOSTNAME"))
    REDIS_PORT: str = str(os.environ.get("REDIS_PORT"))
    REDIS_DB: str = str(os.environ.get("REDIS_DB"))
    REDIS_PASSWORD: str = str(os.environ.get("REDIS_PASSWORD"))

    DATA_DIRECTORY: str = str(os.environ.get("DATA_DIRECTORY"))
    RAW_VIDEO_DIRECTORY: str = str(os.environ.get("RAW_VIDEO_DIRECTORY"))
    RAW_IMAGE_DIRECTORY: str = str(os.environ.get("RAW_IMAGE_DIRECTORY"))
    EXTRACTED_FRAMES_DIRECTORY: str = str(os.environ.get("EXTRACTED_FRAMES_DIRECTORY"))

    USER_FILES_DIRECTORY: str = str(os.environ.get("USER_FILES_DIRECTORY"))

    MODEL_CHECKPOINT_DIRECTORY: str = str(os.environ.get("MODEL_CHECKPOINT_DIRECTORY"))
    MODEL_CONFIG_DIRECTORY: str = str(os.environ.get("MODEL_CONFIG_DIRECTORY"))

    REDIS_MANAGER_QUEUE: str = str(os.environ.get("REDIS_MANAGER_QUEUE"))
    REDIS_MANAGER_STREAM_NAME: str = str(os.environ.get("REDIS_MANAGER_STREAM_NAME"))

    class Config:
        env_file = ".env"


def get_settings():
    settings = Settings()
    # Check if database_url was loaded from the environment variable
    # if settings.database_hostname == "":
    #    settings.database_hostname = os.environ.get("DATABASE_HOST")
    return settings


settings = get_settings()
