import os
import uuid
import shutil
import asyncio
from typing import List, Dict, Optional, Union
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from fastapi.responses import StreamingResponse

import schemas
import database_models as dbmodels
from db import get_db
from utils import get_video_information
from settings import settings
from enums import VideoStatusEnum
from background_tasks import extract_frames, convert_video_to_mp4


router = APIRouter(prefix="/files", tags=["files"])


def get_file_paths_in_directory(directory: str) -> List[str]:
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            # find the absoule path
            abs_path = os.path.abspath(file_path)
            files.append(abs_path)
    return files


@router.get(
    "/available_files",
    response_model=List[schemas.FileOut],
    status_code=status.HTTP_200_OK,
)
async def get_available_files() -> List[schemas.FileOut]:
    final_file_names = []
    # get all file absolute paths including subdirectories
    for root, dirs, filenames in os.walk(settings.USER_FILES_DIRECTORY):
        final_file_names.extend([os.path.abspath(os.path.join(root, filename)) for filename in filenames])
        
        #for d in dirs:
        #    final_file_names.extend(get_file_paths_in_directory(os.path.join(root, d)))
            
            
    out = []
    for abs_file_path in final_file_names:
        file_size = os.path.getsize(abs_file_path)
        out.append(
            schemas.FileOut(
                file_name=os.path.basename(abs_file_path),
                file_path=abs_file_path,
                file_size=file_size,
                created_at=datetime.fromtimestamp(os.path.getctime(abs_file_path))
            )
        )
    
    return out

            
