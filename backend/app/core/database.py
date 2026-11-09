"""Engine factory and session management.

SQLite pragmas (WAL, foreign_keys, synchronous=NORMAL) are applied on every new
connection so behavior does not depend on the database file's persistent state.
PostgreSQL-portability note: only MYCLOUD_DATABASE_URL is provider-specific.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()

_engine: Engine | None = None
_sessionmaker: sessionmaker[Session] | None = None


def _apply_sqlite_pragmas(dbapi_conn: Any, _rec: Any) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_engine() -> Engine:
    """Create (once) the application engine from settings."""
    global _engine, _sessionmaker
    if _engine is None:
        _engine = _create_engine_from_settings()
        _sessionmaker = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def _create_engine_from_settings() -> Engine:
    from sqlalchemy import create_engine

    url = _settings.database_url
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def session_scope() -> Session:
    """Session for repository/service code outside request lifecycle."""
    return get_sessionmaker()()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def database_status() -> dict[str, Any]:
    """Health probe: returns concrete, real diagnostics (no invented data)."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            journal = conn.execute(text("PRAGMA journal_mode")).scalar()
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        return {"reachable": True, "journal_mode": journal, "foreign_keys": bool(fk)}
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        return {"reachable": False, "error": str(exc)}
