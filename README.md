# Hydraulic System Health Monitoring Platform

MLOps-система для диагностики гидравлических систем: FastAPI + asyncpg + PostgreSQL в Docker.

[![CI](https://github.com/xlevando/hydraulic-mlops/actions/workflows/ci.yml/badge.svg)](https://github.com/xlevando/hydraulic-mlops/actions/workflows/ci.yml)
[![CD](https://github.com/xlevando/hydraulic-mlops/actions/workflows/cd.yml/badge.svg)](https://github.com/xlevando/hydraulic-mlops/actions/workflows/cd.yml)

## Стек

- Python 3.14, uv, FastAPI, Pydantic Settings
- asyncpg, PostgreSQL, Docker, Docker Compose
- Ruff, pytest (coverage 100%), pre-commit
- GitHub Actions (CI/CD), GHCR

## Быстрый старт

### Локально

```bash
cp .env.example .env
uv sync --all-groups
uv run uvicorn src.app:app --reload
```

Открыть: http://localhost:8000/docs

### В Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Открыть: http://localhost:8000/docs

## Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/healthz` | Быстрая проверка liveness |
| GET | `/api/v1/version` | Версия приложения |
| GET | `/api/v1/health` | E2E health-check (app + БД) |
| GET | `/docs` | Swagger UI |

## Структура

```
src/
├── app.py              # FastAPI + lifespan
├── config.py           # Pydantic Settings
├── db.py               # asyncpg pool
├── logging_config.py   # логирование с request_id
├── schemas.py          # Pydantic-схемы
├── api/                # эндпоинты
└── services/           # бизнес-логика
tests/                  # pytest (100% coverage)
```

## Тесты

```bash
uv run pytest
```

Coverage: 100%

## CI/CD

- **CI**: ruff + format + tests при push в main и PR
- **CD**: сборка и публикация в GHCR при push тега `v*.*.*`

Релиз:
```bash
git tag v0.1.0
git push origin v0.1.0
```

## Лицензия

MIT
