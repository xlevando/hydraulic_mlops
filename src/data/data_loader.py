"""Загрузка и валидация исходных данных UCI Hydraulic Systems."""

from pathlib import Path

import numpy as np
import pandas as pd

# Сенсор: (частота дискретизации, количество измерений за 60-секундный цикл)
SENSORS: dict[str, tuple[int, int]] = {
    "PS1": (100, 6000),
    "PS2": (100, 6000),
    "PS3": (100, 6000),
    "PS4": (100, 6000),
    "PS5": (100, 6000),
    "PS6": (100, 6000),
    "EPS1": (100, 6000),
    "FS1": (10, 600),
    "FS2": (10, 600),
    "TS1": (1, 60),
    "TS2": (1, 60),
    "TS3": (1, 60),
    "TS4": (1, 60),
    "VS1": (1, 60),
    "CE": (1, 60),
    "CP": (1, 60),
    "SE": (1, 60),
}

PROFILE_COLUMNS = [
    "cooler",
    "valve",
    "pump",
    "accumulator",
    "stable",
]

EXPECTED_CYCLES = 2205


def load_sensor_file(path: Path) -> np.ndarray:
    """Загрузить файл одного сенсора.

    Каждая строка соответствует одному циклу,
    каждая колонка — одному измерению внутри цикла.
    """
    data = pd.read_csv(path, sep="\t", header=None).to_numpy()

    if data.ndim != 2:
        raise ValueError(f"{path}: ожидался двумерный массив, получена форма {data.shape}")

    return data


def load_raw_sensors(data_dir: Path) -> dict[str, np.ndarray]:
    """Загрузить все сенсоры и проверить их размерность."""
    sensors: dict[str, np.ndarray] = {}

    for sensor_name, (_, expected_points) in SENSORS.items():
        path = data_dir / f"{sensor_name}.txt"

        if not path.exists():
            raise FileNotFoundError(f"Не найден файл сенсора: {path}")

        data = load_sensor_file(path)

        expected_shape = (EXPECTED_CYCLES, expected_points)

        if data.shape != expected_shape:
            raise ValueError(
                f"{sensor_name}: ожидалась форма {expected_shape}, получена {data.shape}"
            )

        if not np.isfinite(data).all():
            raise ValueError(f"{sensor_name}: обнаружены NaN или бесконечные значения")

        sensors[sensor_name] = data

    return sensors


def load_profile(data_dir: Path) -> pd.DataFrame:
    """Загрузить состояния компонентов из profile.txt."""
    path = data_dir / "profile.txt"

    if not path.exists():
        raise FileNotFoundError(f"Не найден файл: {path}")

    profile = pd.read_csv(
        path,
        sep=r"\s+",
        header=None,
        names=PROFILE_COLUMNS,
    )

    expected_shape = (EXPECTED_CYCLES, len(PROFILE_COLUMNS))

    if profile.shape != expected_shape:
        raise ValueError(f"profile: ожидалась форма {expected_shape}, получена {profile.shape}")

    if profile.isna().any().any():
        raise ValueError("profile: обнаружены пропущенные значения")

    return profile


def load_dataset(
    data_dir: Path | str,
) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    """Загрузить и провалидировать весь исходный датасет.
    Args:
        data_dir: путь к директории с исходными .txt файлами.
    Returns:
        sensors:
            Словарь вида sensor_name -> массив измерений.
            Форма каждого массива: (2205, n_points).
        profile:
            DataFrame с состояниями компонентов.
    """
    data_dir = Path(data_dir)

    sensors = load_raw_sensors(data_dir)
    profile = load_profile(data_dir)

    n_cycles = len(profile)

    for sensor_name, data in sensors.items():
        if data.shape[0] != n_cycles:
            raise ValueError(
                f"{sensor_name}: количество циклов "
                f"{data.shape[0]} не совпадает с profile "
                f"({n_cycles})"
            )

    return sensors, profile
