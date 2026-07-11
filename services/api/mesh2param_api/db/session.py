from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from .models import Base


class Database:
    def __init__(self, settings: Settings) -> None:
        settings.resolved_data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine = create_engine(
            settings.resolved_database_url,
            connect_args={"check_same_thread": False, "timeout": 30.0},
            pool_pre_ping=True,
        )

        if settings.resolved_database_url.startswith("sqlite:///"):

            @event.listens_for(self.engine, "connect")
            def configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)

    def ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def session(self) -> Iterator[Session]:
        with self.sessions() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()


__all__ = ["Database"]
