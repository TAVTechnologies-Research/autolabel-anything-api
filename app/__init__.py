from settings import settings

from .routers import video_router, ai_model_router, files_router, frames_router, task_router
from .exceptions import CustomHTTPException