import os
import time
import json
import uuid
import shutil
import asyncio

from datetime import datetime, timezone
from typing import List, Dict, Optional, Union, Any, Literal

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

from sqlalchemy.orm import Session


import enums
from enums import annotation
import schemas
import database_models as dbmodels

from db import get_db, get_redis_client, RedisClient
from schemas.annotation import ImageAnnotation
from utils import validate_request
from settings import settings
from ..websocket_manager import WebSocketManager
from ..exceptions import CustomHTTPException

from .frames import get_all_frames

WSMANAGER = WebSocketManager()

REDIS_MANAGER_QUEUE_NAME = os.environ.get("REDIS_MANAGER_QUEUE_NAME")
if not REDIS_MANAGER_QUEUE_NAME:
    raise Exception("REDIS_MANAGER_QUEUE_NAME environment variable not found")
else:
    REDIS_MANAGER_QUEUE_NAME = str(REDIS_MANAGER_QUEUE_NAME)

MAX_SAM2_MODEL_INSTANCES = os.environ.get("MAX_SAM2_MODEL_INSTANCES")
if not MAX_SAM2_MODEL_INSTANCES:
    raise Exception("MAX_SAM2_MODEL_INSTANCES environment variable not found")
else:
    MAX_SAM2_MODEL_INSTANCES = int(MAX_SAM2_MODEL_INSTANCES)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "/status",
    response_model=schemas.TaskStatusResponseCover,
    response_model_exclude_unset=True,
)
async def get_task_status(
    task_uuid: str,
    db: Session = Depends(get_db),
    rcli: RedisClient = Depends(get_redis_client),
) -> schemas.TaskStatusResponseCover:
    # get task status from redis
    task_status = rcli.get(f"task:{task_uuid}:status")
    if not task_status:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Task with uuid {task_uuid} not found"
            ).model_dump(),
        )

    return schemas.TaskStatusResponseCover(
        data=schemas.TaskStatus(status=enums.TaskStatusEnum(task_status)),
    )


@router.get(
    "/",
    response_model=Dict[str, schemas.TaskStatusResponseCover],
    response_model_exclude_unset=True,
)
async def get_all_tasks(
    db: Session = Depends(get_db),
    rcli: RedisClient = Depends(get_redis_client),
) -> Dict[str, schemas.TaskStatusResponseCover]:
    # get all tasks from redis
    task_keys = rcli.get_keys_with_pattern("task:*:status")
    # filter out task keys
    task_keys = [key for key in task_keys if len(key.split(":")) == 3]
    tasks = dict()
    for uuid in task_keys:
        # get status of task
        task_status = rcli.get(uuid)
        if not task_status:
            continue
        tasks[uuid.split(":")[1]] = schemas.TaskStatusResponseCover(
            data=schemas.TaskStatus(status=task_status),  # type: ignore
        )

    return tasks


@router.get(
    "/{task_uuid}",
    response_model=schemas.TaskInformationOutputCover,
)
async def get_task_information(
    task_uuid: str,
    db: Session = Depends(get_db),
) -> schemas.TaskInformationOutputCover:
    task = db.query(dbmodels.Task).filter(dbmodels.Task.task_uuid == task_uuid).first()
    if not task:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Task with uuid {task_uuid} not found"
            ).model_dump(),
        )
    return schemas.TaskInformationOutputCover(
        data=schemas.TaskOut.model_validate(task),
    )


@router.delete(
    "/",
)
async def delete_all_tasks(
    db: Session = Depends(get_db),
    rcli: RedisClient = Depends(get_redis_client),
) -> Response:
    # get all tasks
    tasks: Dict[str, schemas.TaskStatusResponseCover] = await get_all_tasks(db, rcli)
    for task in tasks:
        # delete task
        try:
            is_deleted = await terminate_task(task, rcli=rcli, db=db)
            print(f"Task {task} deleted: {is_deleted}")
        except Exception as err:
            print(f"Error in deleting task {task}: {err}")
            continue
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_uuid}/reset",
)
async def reset_task(
    task_uuid: str,
    scale: Optional[float] = None,
    db: Session = Depends(get_db),
    rcli: RedisClient = Depends(get_redis_client),
) -> Any:
    # check task exists
    task_status = rcli.get(f"task:{task_uuid}:status")
    # TODO: Task checks will be transfered to db
    if not task_status:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Task with uuid {task_uuid} not found"
            ).model_dump(),
        )
    if task_status not in [
        enums.TaskStatusEnum.READY.value,
    ]:
        raise CustomHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=schemas.ErrorResponseCover(
                message=f"Task with uuid {task_uuid} is not ready for reset."
            ).model_dump(),
        )

    rcli.set(f"task:{task_uuid}:status", enums.TaskStatusEnum.BUSY.value)
    # reset task body
    req = schemas.ResetTaskInputCover(
        msg_type="reset",
    )
    is_published = rcli.queue(
        queue_name=f"task:{task_uuid}:request",
        value=req.model_dump_json(),
    )
    if not is_published:
        raise CustomHTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=schemas.ErrorResponseCover(
                message=f"Error in resetting task with uuid {task_uuid}"
            ).model_dump(),
        )

    if not scale:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    # get task config to get video_id
    task_config = rcli.get(f"task:{task_uuid}:config")
    if not task_config:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Task with uuid {task_uuid} not found"
            ).model_dump(),
        )

    try:
        video_id = (
            json.loads(task_config)
            .get("task", dict())
            .get("video", dict())
            .get("video_id", None)
        )
    except Exception as err:
        raise CustomHTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=schemas.ErrorResponseCover(
                message=f"Error in parsing task config for task with uuid {task_uuid}"
            ).model_dump(),
        )
    if not video_id:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Video id not found for task with uuid {task_uuid}"
            ).model_dump(),
        )

    return await get_all_frames(
        video_id=video_id,
        scale=scale,
        start_frame=0,
        end_frame=None,
        thumbnail=True,
        db=db,
        rcli=rcli,
    )


async def _initialize_task(
    init_request: schemas.InitModelRequest,
    db,
    rcli: RedisClient,
) -> Optional[schemas.InitilizeModelResponseCover]:
    aimodel = (
        db.query(dbmodels.AiModel)
        .filter(dbmodels.AiModel.ai_model_id == init_request.ai_model_id)
        .first()
    )
    if not aimodel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI Model with id {init_request.ai_model_id} not found",
        )

    video = (
        db.query(dbmodels.Video)
        .filter(dbmodels.Video.video_id == init_request.video_id)
        .first()
    )
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video with id {init_request.video_id} not found",
        )

    # check video status
    if video.status != enums.VideoStatusEnum.READY.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video with id {init_request.video_id} is not ready for inference",
        )

    # check model initialization count
    # model_init_count = rcli.get(f"model:{aimodel.ai_model_id}:init_count")
    try:
        model_init_count = int(rcli.get("sam2-instances"))  # type: ignore
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model initialization count not found. Check redis confiuguration",
        )

    try:
        max_model_init_count = int(rcli.get("max-sam2-instances"))  # type: ignore
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Maximum model initialization count not found. Check redis confiuguration",
        )

    if model_init_count >= max_model_init_count:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model {aimodel.ai_model_id} has reached maximum initialization count",
        )
    else:
        model_init_count = int(model_init_count)
        # TODO: Initialize model exactly

        try:
            rcli.set("sam2-instances", model_init_count + 1)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error updating model initialization count: {e}",
            )

        task_uuid = str(uuid.uuid4())
        task_intercom = schemas.Intercom(
            task_type=enums.Task.INIT_MODEL.value,
            task=schemas.InitModelIntercom(
                ai_model=aimodel,
                video=video,
            ),
            uuid=task_uuid,
        )

        # is_published = rcli.queue(
        #    str(REDIS_MANAGER_QUEUE_NAME), task_intercom.model_dump_json()
        # )
        # change list add to stream
        is_published = rcli.stream_add(
            stream_name=settings.REDIS_MANAGER_STREAM_NAME,
            data={"task_uuid": task_uuid, "data": task_intercom.model_dump_json()},
        )

        if not is_published:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error publishing task to queue",
            )

        is_config_set = rcli.set(
            f"task:{task_uuid}:config", task_intercom.model_dump_json()
        )
        if not is_config_set:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error setting task config",
            )

        is_published = rcli.set(
            f"task:{task_uuid}:status", enums.TaskStatusEnum.PENDING.value
        )

        if not is_published:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error setting task status",
            )

        is_published = rcli.set(
            f"task:{task_uuid}:annotation:status",
            enums.AnnotationStatusEnum.WAITING.value,
        )
        if not is_published:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error setting task annotation status",
            )

        return schemas.InitilizeModelResponseCover(data=task_intercom)


@router.post(
    "/inference/initialize",
    response_model=schemas.ResponseCover,
    status_code=status.HTTP_200_OK,
)
async def initialize_task(
    init_request: schemas.InitModelRequest,
    db=Depends(get_db),
    rcli=Depends(get_redis_client),
) -> Optional[schemas.InitilizeModelResponseCover]:
    lock = rcli.get_lock("model-init-lock")
    try:
        is_acquired = lock.acquire(blocking=False, blocking_timeout=1)
        if not is_acquired:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Model initialization is in progress. Try again later",
            )
        init_task_response = await _initialize_task(init_request, db, rcli)
        if not init_task_response:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error initializing model",
            )

        if init_task_response.data is not None:
            db_task = dbmodels.Task(
                task_uuid=init_task_response.data.uuid,
                task_name=init_request.task_name,
                video_id=init_request.video_id,
                ai_model_id=init_request.ai_model_id,
                task_config=init_task_response.data.model_dump_json(),
            )
            db.add(db_task)
            db.commit()
            db.refresh(db_task)
        return init_task_response
    except Exception as e:
        if lock.locked() and lock.owned():
            lock.release()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error initializing model: {e}",
        )
    finally:
        if lock.locked() and lock.owned():
            lock.release()


@router.post(
    "/inference/terminate", response_model=None, status_code=status.HTTP_200_OK
)
async def terminate_task(
    task_uuid: str,
    rcli=Depends(get_redis_client),
    db=Depends(get_db),
) -> Optional[Response]:
    # check if task exists
    task_status = rcli.get(f"task:{task_uuid}:status")
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with uuid {task_uuid} not found",
        )
    if task_status in [
        # enums.TaskStatusEnum.FAILED.value,
        enums.TaskStatusEnum.CANCELLED.value,
        enums.TaskStatusEnum.STOPPED.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task with uuid {task_uuid} cannot be terminated at -{task_status}- status",
        )

    # get task from db
    task_db = (
        db.query(dbmodels.Task).filter(dbmodels.Task.task_uuid == task_uuid).first()
    )
    if not task_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with uuid {task_uuid} not found in database",
        )
    task_db.is_active = False
    db.commit()
    db.refresh(task_db)

    terminate_msg = schemas.Intercom(
        task_type=enums.Task.TERMINATE_MODEL.value, uuid=task_uuid, task=None
    )
    # change list add to stream
    is_published = rcli.stream_add(
        stream_name=settings.REDIS_MANAGER_STREAM_NAME,
        data={"task_uuid": task_uuid, "data": terminate_msg.model_dump_json()},
    )
    # is_published = rcli.queue(
    #    f"{REDIS_MANAGER_QUEUE_NAME}", terminate_msg.model_dump_json()
    # )
    if not is_published:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error publishing terminate task to queue",
        )

    return Response(status_code=status.HTTP_200_OK)


@router.websocket("/inference/{task_uuid}")
async def inference_websocket(
    websocket: WebSocket,
    task_uuid: str,
    rcli=Depends(get_redis_client),
    rcli_client=Depends(get_redis_client),
    rcli_server=Depends(get_redis_client),
):
    """Two threads will be created for each websocket connection
    1. One thread will listen user requests
    2. Another thread will deliver responses to the user

    There is an internal queue for these threads' communication

    Args:
        websocket (WebSocket): _description_
        task_uuid (str): _description_
        rcli (_type_, optional): _description_. Defaults to Depends(get_redis_client).

    Raises:
        HTTPException: _description_
    """

    async def user_to_redis_producer(
        task_uuid: str,
        redis_client: RedisClient,
        client_queue: asyncio.Queue[dict],
        server_queue: asyncio.Queue[dict],
    ):
        """
        Delivers user requests to the redis queue to task service can consume

        Args:
            task_uuid (str): UUID of current managed task
            redis_client (RedisClient): Thread-safe Redis client
            client_queue (asyncio.Queue): communcation queue user messages will be stored here
            server_queue (asyncio.Queue): communcation queue server messages will be stored here

        Raises:
            HTTPException: _description_
        """
        try:
            while True:
                try:
                    data = await client_queue.get()
                    # await server_queue.put({"msg": "Received message"})
                    try:
                        parsed_request, is_ok = validate_request(data)
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error validating user request: {e}",
                        )
                    if is_ok:
                        redis_client.queue(
                            f"task:{task_uuid}:request",
                            parsed_request.model_dump_json(),
                        )
                    else:
                        await server_queue.put(parsed_request.model_dump())

                except asyncio.QueueEmpty:
                    pass
                except Exception as e:
                    # raise HTTPException(
                    #    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    #    detail=f"Error delivering user request to redis: {e}",
                    # )
                    raise WebSocketException(
                        code=status.WS_1011_INTERNAL_ERROR,
                        reason=f"Error delivering user request to redis: {e}",
                    )
        except asyncio.CancelledError:
            print("user_to_redis_producer task cancelled")
        except Exception as e:
            # raise HTTPException(
            #    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            #    detail=f"Error delivering user request to redis: {e}",
            # )
            raise WebSocketException(
                code=status.WS_1011_INTERNAL_ERROR,
                reason=f"Error delivering user request to redis: {e}",
            )

    async def redis_to_user_consumer(
        task_uuid: str,
        redis_client: RedisClient,
        client_queue: asyncio.Queue[dict],
        server_queue: asyncio.Queue[dict],
    ):
        """
        Consumes redis queue to deliver responses to the user via internal queue
        for websocket manager can deliver the message to the user

        Args:
            task_uuid (str): UUID of current managed task
            redis_client (RedisClient): Thread-safe Redis client
            client_queue (asyncio.Queue): communcation queue user messages will be stored here
            server_queue (asyncio.Queue): communcation queue server messages will be stored here

        Raises:
            HTTPException: _description_
        """
        try:
            while True:
                try:
                    data = redis_client.dequeue(f"task:{task_uuid}:response", count=1)
                    if not data:
                        await asyncio.sleep(0.1)
                        continue
                    await server_queue.put(data[0].decode("utf-8"))  # type: ignore
                except asyncio.QueueFull:
                    pass  # Remember: Handle full queue case in the future
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error consuming redis response: {e}",
                    )
        except asyncio.CancelledError:
            print("redis_to_user_consumer task cancelled")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error consuming redis response: {e}",
            )

    # TODO: All redis communcations must be async

    await WSMANAGER.connect(websocket)
    # before creating corutines check if task exists
    task_status = rcli.get(f"task:{task_uuid}:status")
    print(f"Task status: {task_status}")
    if not task_status:
        print(f"Task with uuid {task_uuid} not found")
        await WSMANAGER.disconnect(websocket)
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Task with uuid {task_uuid} not found",
        )

    if task_status in [
        enums.TaskStatusEnum.FAILED.value,
        enums.TaskStatusEnum.CANCELLED.value,
        enums.TaskStatusEnum.STOPPED.value,
    ]:
        # TODO: deliver a error response cover not a string
        # await websocket.send_text(f"Task with uuid {task_uuid} terminated")
        await WSMANAGER.disconnect(websocket)
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Task with uuid {task_uuid} cannot be used at -{task_status}- status",
        )

    user_to_redis_producer_task = asyncio.create_task(
        user_to_redis_producer(
            task_uuid,
            rcli_client,
            client_queue=WSMANAGER.communication_queues[websocket]["client"],
            server_queue=WSMANAGER.communication_queues[websocket]["server"],
        )
    )
    redis_to_user_consumer_task = asyncio.create_task(
        redis_to_user_consumer(
            task_uuid,
            rcli_server,
            client_queue=WSMANAGER.communication_queues[websocket]["client"],
            server_queue=WSMANAGER.communication_queues[websocket]["server"],
        )
    )

    receive_task = asyncio.create_task(WSMANAGER.receive_message(websocket))
    send_task = asyncio.create_task(WSMANAGER.send_message(websocket))

    try:

        await asyncio.gather(
            receive_task,
            send_task,
            user_to_redis_producer_task,
            redis_to_user_consumer_task,
        )

    except WebSocketDisconnect:
        print("*** WebSocket exception ***")
        # WSMANAGER.disconnect(websocket)
        pass
    finally:
        await WSMANAGER.disconnect(websocket)
        user_to_redis_producer_task.cancel()
        redis_to_user_consumer_task.cancel()
        receive_task.cancel()
        send_task.cancel()


# FIXME: Multiple exports must be handled -> overwriting the previous one
@router.post("/export/{task_uuid}", status_code=status.HTTP_200_OK)
async def export_task_annotation(
    task_uuid: str,
    overwrite: bool = True,
    db=Depends(get_db),
    rcli=Depends(get_redis_client),
) -> Any:
    annotations = await get_annotations(
        task_uuid, annotation_format="all", db=db, rcli=rcli
    )
    if not annotations:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Annotations for task with uuid {task_uuid} not found"
            ).model_dump(),
        )
    if not annotations.data:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Annotations for task with uuid {task_uuid} not found"
            ).model_dump(),
        )

    # get task id by uuid
    task = db.query(dbmodels.Task).filter(dbmodels.Task.task_uuid == task_uuid).first()
    if not task:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Task with uuid {task_uuid} not found in the db. Cannot export."
            ).model_dump(),
        )

    # check if the data exported before
    if task.exported_at:
        if not overwrite:
            raise CustomHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=schemas.ErrorResponseCover(
                    message=f"Task with uuid {task_uuid} is already exported at {task.exported_at}"
                ).model_dump(),
            )

    rows = []
    for anno in annotations.data:
        if task.exported_at:
            existing_annotation = (
                db.query(dbmodels.Annotation)
                .filter(
                    dbmodels.Annotation.task_id == task.task_id,
                    dbmodels.Annotation.image_id == anno.image_id,
                )
                .first()
            )
            if existing_annotation:
                existing_annotation.annotation_data = anno.model_dump_json()
                existing_annotation.annotated_at = anno.meta.annotated_at
                continue

        annotation_row = dbmodels.Annotation(
            task_id=task.task_id,
            image_id=anno.image_id,
            image_path=anno.image_path,
            annotation_data=anno.model_dump_json(),
            annotation_type="all",
            frame_idx=anno.meta.frame_idx,
            annotated_at=anno.meta.annotated_at,
        )
        rows.append(annotation_row)

    if rows:
        db.bulk_save_objects(rows)
        
    task.exported_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/annotation/status", status_code=status.HTTP_200_OK)
async def get_annotation_status(
    task_uuid: str, db=Depends(get_db), rcli=Depends(get_redis_client)
) -> schemas.AnnotationStatusResponseCover:

    # get task status from redis
    annotation_status = rcli.get(f"task:{task_uuid}:annotation:status")
    if not annotation_status:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Annotation for task with uuid {task_uuid} not found"
            ).model_dump(),
        )
    return schemas.AnnotationStatusResponseCover(
        data=schemas.AnnotationStatus(
            status=enums.AnnotationStatusEnum(annotation_status)
        ),
    )


@router.get("/annotation/", status_code=status.HTTP_200_OK)
async def get_annotations(
    task_uuid: str,
    annotation_format: Literal["all", "bbox", "polygon"] = "all",
    db=Depends(get_db),
    rcli: RedisClient = Depends(get_redis_client),
) -> schemas.ImageAnnotationResponseCover:
    start = time.time()
    # get annotation status
    annotation_status = rcli.get(f"task:{task_uuid}:annotation:status")
    if not annotation_status:
        raise CustomHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=schemas.ErrorResponseCover(
                message=f"Annotation for task with uuid {task_uuid} not found"
            ).model_dump(),
        )

    if annotation_status not in [
        enums.AnnotationStatusEnum.READY.value,
    ]:
        raise CustomHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=schemas.ErrorResponseCover(
                message=f"Annotation for task with uuid {task_uuid} is not ready for export.\nOnly 'ready' annotations can be exported."
            ).model_dump(),
        )

    # get annotation keys
    # keys_to_retrieve = rcli.get_keys_with_pattern(f"task:{task_uuid}:annotation:*")
    raw_annotations = rcli.get_values_with_pattern(
        f"task:{task_uuid}:annotation:[0-9]*"
    )
    annotations: List[ImageAnnotation] = list()
    for anno in raw_annotations:
        try:
            model = schemas.ImageAnnotation.model_validate_json(anno)
            if annotation_format == "bbox":
                model.polygon_annotations = list()
            elif annotation_format == "polygon":
                model.bbox_annotations = list()
            annotations.append(model)
        except Exception as e:
            print(f"Error in validating annotation: {e}")
            continue
    end = time.time()
    print(f"Elapsed time: {end-start}")
    return schemas.ImageAnnotationResponseCover(data=annotations)
