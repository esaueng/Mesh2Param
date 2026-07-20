from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings


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
        configuration = Config()
        configuration.set_main_option(
            "script_location",
            str(Path(__file__).resolve().parents[1] / "migrations"),
        )
        configuration.attributes["connection"] = self.engine
        table_names = set(inspect(self.engine).get_table_names())
        if table_names and "alembic_version" not in table_names:
            # Releases before Alembic already match the frozen baseline. Stamp
            # that revision, then apply every explicit migration after it.
            command.stamp(configuration, "0001_initial")
        command.upgrade(configuration, "head")

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
