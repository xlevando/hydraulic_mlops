"""Управление пулом соединений с PostgreSQL (asyncpg)."""

import logging

import asyncpg

from src.config import get_settings

log = logging.getLogger(__name__)


async def create_db_pool() -> asyncpg.Pool:
    """Создать пул соединений с PostgreSQL.

    `min_size=0` — при старте не подключаемся: приложение поднимется,
    даже если БД недоступна.
    """
    settings = get_settings()
    pool = await asyncpg.create_pool(
        settings.database.url,
        min_size=settings.database.min_size,
        max_size=settings.database.max_size,
        command_timeout=settings.database.command_timeout,
    )
    log.info("Пул соединений с PostgreSQL создан")
    return pool


async def close_db_pool(pool: asyncpg.Pool) -> None:
    """Закрыть пул и все его соединения."""
    await pool.close()
    log.info("Пул соединений с PostgreSQL закрыт")
