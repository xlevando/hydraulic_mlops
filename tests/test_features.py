"""Тесты src/data/features.py."""

import numpy as np
import pandas as pd
import pytest

from src.data.features import (
    add_cycle_id,
    build_features,
    extract_features,
)


def test_extract_features_returns_dict() -> None:
    """Возвращает dict."""
    signal = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    features = extract_features(signal, sampling_rate=1.0)

    assert isinstance(features, dict)
    assert "mean" in features
    assert "std" in features
    assert "rms" in features


def test_extract_features_mean_correct() -> None:
    """Среднее считается верно."""
    signal = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    features = extract_features(signal, sampling_rate=1.0)

    assert features["mean"] == 3.0


def test_extract_features_rms_correct() -> None:
    """RMS = sqrt(mean(x²))."""
    signal = np.array([3.0, 4.0])
    features = extract_features(signal, sampling_rate=1.0)

    assert features["rms"] == pytest.approx(np.sqrt((9 + 16) / 2))


def test_extract_features_slope_correct() -> None:
    """Slope = (x[-1] - x[0]) / duration."""
    signal = np.array([0.0, 5.0])
    # duration = 2/1.0 = 2.0
    # slope = (5 - 0) / 2 = 2.5
    features = extract_features(signal, sampling_rate=1.0)

    assert features["slope"] == 2.5


def test_extract_features_empty_signal() -> None:
    """Пустой сигнал — ошибка."""
    with pytest.raises(ValueError):
        extract_features(np.array([]), sampling_rate=1.0)


def test_extract_features_one_point() -> None:
    """Одна точка — ошибка."""
    with pytest.raises(ValueError):
        extract_features(np.array([1.0]), sampling_rate=1.0)


def test_extract_features_wrong_dimension() -> None:
    """2D — ошибка."""
    with pytest.raises(ValueError):
        extract_features(np.array([[1.0, 2.0]]), sampling_rate=1.0)


def test_extract_features_invalid_sampling_rate() -> None:
    """sampling_rate <= 0 — ошибка."""
    with pytest.raises(ValueError):
        extract_features(np.array([1.0, 2.0]), sampling_rate=0.0)


def test_add_cycle_id_inserts_column() -> None:
    """cycle_id добавляется."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = add_cycle_id(df)

    assert "cycle_id" in result.columns
    assert list(result["cycle_id"]) == [0, 1, 2]
    assert result.shape == (3, 3)


def test_build_features_correct_shape() -> None:
    """Форма = n_cycles x (n_sensors x n_features)."""
    sensors = {
        "PS1": np.random.rand(5, 10),
        "FS1": np.random.rand(5, 10),
    }
    sensor_config = {
        "PS1": (100, 10),
        "FS1": (10, 10),
    }
    result = build_features(sensors, sensor_config)

    # 5 циклов × 2 сенсора × 10 признаков = 100 колонок
    assert result.shape == (5, 20)  # 2 × 10 = 20
