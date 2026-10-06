"""API-эндпоинт для диагностики гидравлической системы."""

import logging

import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from src.schemas import ProcessRequest, ProcessResponse

log = logging.getLogger(__name__)

process_router = APIRouter(
    prefix="/api/v1",
    tags=["process"],
)


@process_router.post(
    "/process",
    response_model=ProcessResponse,
)
async def process(
    request: Request,
    payload: ProcessRequest,
) -> ProcessResponse:
    """Предсказать состояние компонентов гидравлической системы."""

    models = request.app.state.models

    if not models:
        raise HTTPException(
            status_code=503,
            detail="Models are not loaded",
        )

    # Все модели обучались на одном и том же наборе из 170 признаков.
    reference_model = next(iter(models.values()))

    expected_features = list(reference_model.feature_names_in_)

    received_features = set(payload.features)

    missing_features = set(expected_features) - received_features

    unexpected_features = received_features - set(expected_features)

    if missing_features or unexpected_features:
        detail = {}

        if missing_features:
            detail["missing_features"] = sorted(missing_features)

        if unexpected_features:
            detail["unexpected_features"] = sorted(unexpected_features)

        raise HTTPException(
            status_code=422,
            detail=detail,
        )

    # DataFrame создаём в том же порядке признаков,
    # в котором модель видела их при обучении.
    X = pd.DataFrame(  # noqa: N806
        [[payload.features[feature] for feature in expected_features]],
        columns=expected_features,
    )

    predictions: dict[str, int] = {}

    for target, model in models.items():
        prediction = model.predict(X)[0]
        predictions[target] = int(prediction)

    log.info(
        "Hydraulic system processed: predictions=%s",
        predictions,
    )

    return ProcessResponse(
        predictions=predictions,
    )
