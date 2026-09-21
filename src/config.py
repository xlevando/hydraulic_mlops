from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

type Environment = Literal["development", "staging", "production"]
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Корень проекта (на 2 уровня выше: src/config.py => src/ => корень)
BASE_DIR = Path(__file__).resolve().parent.parent


class AppSettings(BaseModel):
    name: str = "hydraulic-mlops"
    version: str = "0.1.0"
    description: str = "FastAPI-сервис. MLOps-система диагностики гидравлических систем"
    debug: bool = False


class DatabaseSettings(BaseModel):
    url: str = Field(
        default="postgresql://postgres:postgres@localhost:5433/hydraulic_mlops",
        description="Строка подключения к Postgres (asyncpg)",
    )
    min_size: int = Field(
        default=0,
        description="Минимум соединений в пуле; 0 — не подключаться на старте.",
    )
    max_size: int = Field(
        default=10,
        description="Максимум соединений в пуле — потолок нагрузки на БД.",
    )
    command_timeout: float = Field(
        default=5.0,
        description="Таймаут одного запроса, секунды.",
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=str(BASE_DIR / "config.yaml"),
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    log_level: LogLevel = "INFO"
    environment: Environment = "development"

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YamlConfigSettingsSource(settings_cls),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
