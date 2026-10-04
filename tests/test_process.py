"""Тесты /api/v1/process."""

import pytest
from httpx import AsyncClient

# 170 признаков
SENSORS = [
    "PS1",
    "PS2",
    "PS3",
    "PS4",
    "PS5",
    "PS6",
    "EPS1",
    "FS1",
    "FS2",
    "TS1",
    "TS2",
    "TS3",
    "TS4",
    "VS1",
    "CE",
    "CP",
    "SE",
]
STATS = ["mean", "std", "rms", "min", "max", "median", "skew", "kurtosis", "delta", "slope"]
FEATURES = [f"{s}_{st}" for s in SENSORS for st in STATS]


@pytest.mark.asyncio
async def test_process_ok(client: AsyncClient) -> None:
    """POST /process возвращает предсказания."""
    features = {f: 1.0 for f in FEATURES}

    response = await client.post("/api/v1/process", json={"features": features})

    assert response.status_code == 200
    assert set(response.json()["predictions"]) == {"cooler", "valve", "pump", "accumulator"}


@pytest.mark.asyncio
async def test_process_missing_features(client: AsyncClient) -> None:
    """POST /process — 422 при отсутствии признаков."""
    features = {f: 1.0 for f in FEATURES[:-5]}  # убрали 5

    response = await client.post("/api/v1/process", json={"features": features})

    assert response.status_code == 422
