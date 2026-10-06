"""
Построить полноценный датасет для дальнейшей работы из сырых данных сенсоров и сохранить в CSV.
Запуск по : uv run python -m scripts.build_dataset
"""

from pathlib import Path

from src.data.data_loader import SENSORS, load_dataset
from src.data.features import build_feature_dataset


def main() -> None:
    """Загрузить сенсоры, извлечь признаки, сохранить в data/processed."""
    data_dir = Path("data/raw")
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(" 1. Загрузка сенсоров")
    sensors, profile = load_dataset(data_dir)
    print(f"  Сенсоров: {len(sensors)}")
    print(f"  Циклов: {len(profile)}")
    print(f"  Колонки profile: {list(profile.columns)}")

    print()
    print(" 2. Извлечение признаков")
    x = build_feature_dataset(sensors, SENSORS)
    print(f"  X: {x.shape}")
    print(f"  Первые 5 колонок: {list(x.columns[:5])}")

    print()
    print(" 3. Сохранение")
    x.to_csv(output_dir / "X.csv", index=False)
    profile.to_csv(output_dir / "y.csv", index=False)
    print(f"  X.csv: {output_dir / 'X.csv'} ({x.shape})")
    print(f"  y.csv: {output_dir / 'y.csv'} ({profile.shape})")


if __name__ == "__main__":
    main()
