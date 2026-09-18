import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=_json_default)


def from_json(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def row_to_json(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _convert_value(value) for key, value in row.items()}


def _convert_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_convert_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _convert_value(item) for key, item in value.items()}
    return value


class Database:
    """Small query helper around psycopg.

    The service is intentionally simple for teaching: routers call this helper
    directly instead of hiding SQL behind several repository layers.
    """

    def __init__(self) -> None:
        self._url = get_settings().business_database_url

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            yield conn

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.rowcount


db = Database()

