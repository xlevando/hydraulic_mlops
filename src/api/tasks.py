"""API-эндпоинт для публикации задач в очередь RabbitMQ."""

import os
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status

from src.broker import TASKS_QUEUE, broker
from src.schemas import TaskAcceptedResponse, TaskRequest

log = structlog.get_logger()

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
    """Опубликовать задачу в очередь."""
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

    task_id = uuid.uuid4().hex[:12]

    try:
        await broker.publish(
            {"task_id": task_id, "features": payload.features},
            queue=TASKS_QUEUE,
        )
    except Exception as e:
        # ВРЕМЕННО: логируем настоящую ошибку, чтобы понять, что падает
        log.error("Publish failed with REAL error", exc_info=True, error=str(e))
        raw = os.getenv("RETRY_AFTER_SEC") or os.getenv("INFERENCE_DELAY_SEC") or "5"
        try:
            retry_after = max(1, int(float(raw)))
        except TypeError, ValueError:
            retry_after = 5
        log.warning(
            "Publish rejected (queue overloaded)",
            retry_after=retry_after,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Queue overloaded. Retry after {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        ) from e

    log.info("Task accepted", task_id=task_id)
    return TaskAcceptedResponse(task_id=task_id)
