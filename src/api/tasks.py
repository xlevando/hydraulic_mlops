"""API-эндпоинт для публикации задач в очередь RabbitMQ.

Load shedding: при перегрузке очереди API немедленно возвращает 503
с заголовком Retry-After, не принимая задачу в обработку.

Валидация признаков происходит здесь (fail fast) — до публикации
в очередь (экономия ресурсов очереди и воркера)
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status

from src.broker import TASKS_QUEUE, broker
from src.schemas import TaskAcceptedResponse, TaskRequest

log = logging.getLogger(__name__)

tasks_router = APIRouter(
    prefix="/api/v1",
    tags=["tasks"],
)


@tasks_router.post(
    "/tasks",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_task(
    request: Request,
    response: Response,
    payload: TaskRequest,
) -> TaskAcceptedResponse:
    """Опубликовать задачу в очередь.
    Load shedding:
        Если очередь переполнена, API возвращает 503 + Retry-After.
        Задача не остаётся в системе в состоянии PENDING.
    """
    # валидация признаков (fail fast)
    models = request.app.state.models

    if not models:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Models are not loaded",
        )

    reference_model = next(iter(models.values()))
    expected_features = set(reference_model.feature_names_in_)
    received_features = set(payload.features.keys())

    missing = expected_features - received_features
    unexpected = received_features - expected_features

    if missing or unexpected:
        detail = {}
        if missing:
            detail["missing_features"] = sorted(missing)
        if unexpected:
            detail["unexpected_features"] = sorted(unexpected)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        )

    #  публикация в очередь
    task_id = uuid.uuid4().hex[:12]

    try:
        await broker.publish(
            {"task_id": task_id, "features": payload.features},
            queue=TASKS_QUEUE,
        )
    except Exception as e:
        log.warning("Publish rejected (queue overloaded): %s", e)
        response.headers["Retry-After"] = "60"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Queue overloaded. Retry after 60s.",
        ) from e

    log.info("Task %s accepted", task_id)
    return TaskAcceptedResponse(task_id=task_id)
