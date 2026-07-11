from __future__ import annotations

from .config import Settings
from .db import Database


def main() -> int:
    settings = Settings()
    database = Database(settings)
    try:
        database.migrate()
        print(f"Mesh2Param database ready: {settings.resolved_database_url}")
        return 0
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
