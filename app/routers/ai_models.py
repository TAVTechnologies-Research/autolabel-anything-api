import os
from socket import timeout
import time
import uuid
import shutil
import asyncio
from typing import List, Dict, Optional, Union, Any, final
from datetime import datetime


from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocketException,
    status,
    BackgroundTasks,
    Response,
    WebSocket,
    WebSocketDisconnect,
)

import enums
import schemas
import database_models as dbmodels
from utils import validate_request
from db import get_db, get_redis_client, RedisClient
from ..websocket_manager import WebSocketManager
from settings import settings


router = APIRouter(prefix="/ai-models", tags=["ai-models"])


@router.get(
    "/all", response_model=List[schemas.AiModel], status_code=status.HTTP_200_OK
)
async def get_all_ai_models(db=Depends(get_db)) -> List[schemas.AiModel]:
    aimodels = db.query(dbmodels.AiModel).order_by(dbmodels.AiModel.ai_model_id).all()
    return aimodels


@router.get(
    "/{ai_model_id}", response_model=schemas.AiModel, status_code=status.HTTP_200_OK
)
async def get_ai_model_by_id(ai_model_id: int, db=Depends(get_db)) -> schemas.AiModel:
    aimodel = (
        db.query(dbmodels.AiModel)
        .filter(dbmodels.AiModel.ai_model_id == ai_model_id)
        .first()
    )
    if not aimodel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI Model with id {ai_model_id} not found",
        )
    return aimodel


@router.post(
    "/add", response_model=schemas.AiModel, status_code=status.HTTP_201_CREATED
)
async def add_ai_model(
    ai_model: schemas.AiModel, db=Depends(get_db)
) -> schemas.AiModel:
    new_model = dbmodels.AiModel(
        model_name=ai_model.ai_model_name,
        checkpoint_path=ai_model.checkpoint_path,
        config_path=ai_model.config_path,
    )
    db.add(new_model)
    db.commit()
    db.refresh(new_model)
    return new_model
