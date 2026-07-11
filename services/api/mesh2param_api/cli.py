from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn

from .app import create_app
from .config import Settings


def run_server(
    *, host: str | None = None, port: int | None = None, reload: bool = False
) -> int:
    settings = Settings()
    bind_host = host or settings.bind_host
    bind_port = port or settings.port
    if reload:
        uvicorn.run(
            "mesh2param_api.app:create_app",
            factory=True,
            host=bind_host,
            port=bind_port,
            reload=True,
            log_level=settings.log_level.lower(),
        )
    else:
        uvicorn.run(
            create_app(settings),
            host=bind_host,
            port=bind_port,
            log_level=settings.log_level.lower(),
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh2param-api")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    return run_server(host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_server"]
