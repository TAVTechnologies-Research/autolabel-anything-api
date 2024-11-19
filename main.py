import os
import json
import dotenv
from numpy import isin

from db.redis_client import RedisClient

dotenv.load_dotenv(".env.general")
print(f"ENVIRONMENT: {os.environ.get('MAX_SAM2_MODEL_INSTANCES')}")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

import database_models as dbmodels
from db import Base, engine, get_db, get_redis_client
from app import CustomHTTPException
from app import video_router, ai_model_router, files_router, frames_router, task_router
from settings import settings

from pydantic import BaseModel
from typing import Any, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse


# Define the standardized response model
##class StandardResponseModel(BaseModel):
##    msg_type: str
##    data: Optional[Any] = None
##    error: Optional[str] = None
##    meta: Optional[Any] = None
##
### Custom middleware to wrap all responses
##class ResponseWrapperMiddleware(BaseHTTPMiddleware):
##    async def dispatch(self, request: Request, call_next):
##        try:
##            print(f"Request: {request.url.path}")
##            # Process the request and get the response
##            response = await call_next(request)
##
##            if response.headers.get("X-Stream", "false") == "true":
##                return response
##
##            # Extract the response body
##            if hasattr(response, 'body_iterator'):
##                body = b""
##                async for chunk in response.body_iterator:
##                    body += chunk
##                response_body = body.decode()
##            else:
##                response_body = await response.body()
##
##            # Determine response type and wrap it
##            if response.status_code == 200:
##                try:
##                    data = json.loads(response_body)
##                except json.JSONDecodeError:
##                    data = response_body if response_body else None
##
##                wrapped_response = StandardResponseModel(
##                    msg_type="success",
##                    data=data,
##                    error=None,
##                    meta={"path": request.url.path}
##                )
##            else:
##                wrapped_response = StandardResponseModel(
##                    msg_type="error",
##                    data=None,
##                    error=response_body,
##                    meta={"path": request.url.path}
##                )
##
##            return JSONResponse(status_code=response.status_code, content=wrapped_response.dict())
##        except Exception as e:
##            # Handle exceptions and return standardized error response
##            wrapped_response = StandardResponseModel(
##                msg_type="error",
##                data=None,
##                error=str(e),
##                meta={"path": request.url.path}
##            )
##            return JSONResponse(status_code=500, content=wrapped_response.dict())
##


def init_folder_structure() -> None:
    os.makedirs(settings.DATA_DIRECTORY, exist_ok=True)
    os.makedirs(settings.RAW_VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(settings.RAW_IMAGE_DIRECTORY, exist_ok=True)
    os.makedirs(settings.EXTRACTED_FRAMES_DIRECTORY, exist_ok=True)


def init_redis_structure() -> None:
    rcli = get_redis_client()
    if not isinstance(rcli, RedisClient):
        raise RuntimeError("Error connecting to redis")
    # create stream
    # rcli.stream_add(settings.REDIS_MANAGER_STREAM_NAME, {"data": ""})
    pub_id = rcli.client.xadd(settings.REDIS_MANAGER_STREAM_NAME, {"data": ""})
    print(f"Stream created: {pub_id}")
    # remove dummy message
    rcli.client.xdel(settings.REDIS_MANAGER_STREAM_NAME, pub_id)
    # create a consumer group
    try:
        rcli.client.xgroup_create(
            name=settings.REDIS_MANAGER_STREAM_NAME,
            groupname="main",
            id="0",
            mkstream=True,
        )
    except Exception as e:
        print(f"Error creating consumer group: {e}")
        



init_folder_structure()
Base.metadata.create_all(bind=engine)
init_redis_structure()

app = FastAPI(
    debug=True,
    title="Segment Anything API",
)
# app.add_middleware(ResponseWrapperMiddleware)


@app.exception_handler(CustomHTTPException)
async def custom_http_exception_handler(request: Request, exc: CustomHTTPException):
    exc.headers["Content-Type"] = "application/json"  # type: ignore
    return Response(
        status_code=exc.status_code,
        content=json.dumps(exc.detail) if isinstance(exc.detail, dict) else exc.detail,
        headers=exc.headers,
    )


origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video_router)
app.include_router(ai_model_router)
app.include_router(files_router)
app.include_router(frames_router)
app.include_router(task_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}
