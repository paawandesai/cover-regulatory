from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def _conninfo() -> str:
    # psycopg wants a libpq URL; accept SQLAlchemy-style "postgresql+psycopg://" too.
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(_conninfo(), row_factory=dict_row) as conn:
        yield conn
