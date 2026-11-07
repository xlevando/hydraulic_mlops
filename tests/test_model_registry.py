"""Тесты src/services/model_registry.py."""

from unittest.mock import MagicMock, patch

from src.services import model_registry


def test_load_champion_models_returns_four_models() -> None:
    """load_champion_models возвращает 4 модели."""
    with patch("src.services.model_registry.mlflow") as mock_mlflow:
        mock_mlflow.sklearn.load_model.return_value = MagicMock()

        result = model_registry.load_champion_models()

        assert set(result.keys()) == {
            "cooler",
            "valve",
            "pump",
            "accumulator",
        }


def test_get_tracking_uri_from_env() -> None:
    """get_tracking_uri читает env."""
    with patch.dict("os.environ", {"MLFLOW_TRACKING_URI": "http://custom:5000"}):
        uri = model_registry.get_tracking_uri()
        assert uri == "http://custom:5000"


def test_get_tracking_uri_default() -> None:
    """get_tracking_uri fallback."""
    with patch.dict("os.environ", {}, clear=True):
        uri = model_registry.get_tracking_uri()
        assert uri == "http://localhost:5001"
