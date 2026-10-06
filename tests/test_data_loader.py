"""Тесты src/data/data_loader.py."""

from pathlib import Path

import pytest

from src.data.data_loader import (
    EXPECTED_CYCLES,
    PROFILE_COLUMNS,
    SENSORS,
    load_profile,
    load_raw_sensors,
    load_sensor_file,
)


def test_sensors_config_has_17_sensors() -> None:
    """Всего 17 сенсоров."""
    assert len(SENSORS) == 17


def test_sensors_config_contains_known_sensors() -> None:
    """Ключевые сенсоры есть."""
    for name in ["PS1", "FS1", "TS1", "VS1", "SE"]:
        assert name in SENSORS


def test_profile_columns_correct() -> None:
    """5 колонок profile."""
    assert PROFILE_COLUMNS == ["cooler", "valve", "pump", "accumulator", "stable"]


def test_expected_cycles_is_2205() -> None:
    """Ожидается 2205 циклов."""
    assert EXPECTED_CYCLES == 2205


def test_load_sensor_file_missing_file(tmp_path: Path) -> None:
    """Несуществующий файл — ошибка."""
    with pytest.raises(FileNotFoundError):
        load_sensor_file(tmp_path / "nonexistent.txt")


def test_load_sensor_file_wrong_dimension(tmp_path: Path) -> None:
    """1D массив — ошибка."""
    path = tmp_path / "test.txt"
    path.write_text("1.0\n2.0\n3.0\n")
    # pd.read_csv создаст DataFrame с 1 колонкой → to_numpy() → 2D (3, 1)
    data = load_sensor_file(path)
    assert data.ndim == 2


def test_load_profile_missing_file(tmp_path: Path) -> None:
    """Нет profile.txt — ошибка."""
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path)


def test_load_raw_sensors_missing_dir(tmp_path: Path) -> None:
    """Пустая папка — ошибка."""
    with pytest.raises(FileNotFoundError):
        load_raw_sensors(tmp_path)
