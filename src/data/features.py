"""Извлечение признаков из сигналов UCI Hydraulic Systems"""

import numpy as np
import pandas as pd
from scipy import stats


def extract_features(
    signal: np.ndarray,
    sampling_rate: float,
) -> dict[str, float]:
    """Извлечь базовые статистические и временные признаки.
    Args:
        signal: одномерный сигнал одного цикла.
        sampling_rate: частота дискретизации в Hz.
    Returns:
        Словарь с рассчитанными признаками.
    """
    if signal.ndim != 1:
        raise ValueError(f"Ожидался одномерный сигнал, получена форма {signal.shape}")

    if len(signal) < 2:
        raise ValueError("Для извлечения признаков нужно минимум 2 точки")

    if sampling_rate <= 0:
        raise ValueError("sampling_rate должен быть положительным")

    duration = len(signal) / sampling_rate

    skew = stats.skew(signal)
    kurtosis = stats.kurtosis(signal)

    # Для константного сигнала scipy может вернуть NaN.
    # В этом случае асимметрия и excess kurtosis принимаются равными 0.
    if not np.isfinite(skew):
        skew = 0.0

    if not np.isfinite(kurtosis):
        kurtosis = 0.0

    return {
        "mean": float(np.mean(signal)),
        "std": float(np.std(signal)),
        "rms": float(np.sqrt(np.mean(signal**2))),
        "min": float(np.min(signal)),
        "max": float(np.max(signal)),
        "median": float(np.median(signal)),
        "skew": float(skew),
        "kurtosis": float(kurtosis),
        "delta": float(signal[-1] - signal[0]),
        "slope": float((signal[-1] - signal[0]) / duration),
    }


def build_features(
    sensors: dict[str, np.ndarray],
    sensor_config: dict[str, tuple[int, int]],
) -> pd.DataFrame:
    """Построить cycle-level feature dataset.
    Для каждого сенсора и каждого цикла рассчитываются
    статистические и временные признаки.
    Args:
        sensors:
            Словарь sensor_name => массив сигналов.
        sensor_config:
            Конфигурация сенсоров:
            sensor_name => (sampling_rate, n_points).
    Returns:
        Датафрейм размера: n_cycles x (n_sensors x n_features)
    """
    if not sensors:
        raise ValueError("Словарь sensors пуст")

    n_cycles = next(iter(sensors.values())).shape[0]

    rows: list[dict[str, float]] = []

    for cycle_idx in range(n_cycles):
        row: dict[str, float] = {}

        for sensor_name, signal_data in sensors.items():
            if sensor_name not in sensor_config:
                raise ValueError(f"Нет конфигурации для сенсора {sensor_name}")

            sampling_rate, expected_points = sensor_config[sensor_name]

            signal = signal_data[cycle_idx]

            if len(signal) != expected_points:
                raise ValueError(
                    f"{sensor_name}: цикл {cycle_idx} содержит "
                    f"{len(signal)} точек вместо "
                    f"{expected_points}"
                )

            features = extract_features(
                signal=signal,
                sampling_rate=sampling_rate,
            )

            for feature_name, value in features.items():
                row[f"{sensor_name}_{feature_name}"] = value

        rows.append(row)

    return pd.DataFrame(rows)


def add_cycle_id(features: pd.DataFrame) -> pd.DataFrame:
    """Добавить идентификатор цикла."""
    result = features.copy()

    result.insert(
        0,
        "cycle_id",
        np.arange(len(result)),
    )

    return result


def build_feature_dataset(
    sensors: dict[str, np.ndarray],
    sensor_config: dict[str, tuple[int, int]],
) -> pd.DataFrame:
    """Построить полный cycle-level датасет признаков."""
    features = build_features(
        sensors=sensors,
        sensor_config=sensor_config,
    )

    return add_cycle_id(features)
