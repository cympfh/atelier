"""CLI entrypoint: `atelier start`."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from atelier import __version__
from atelier.config import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atelier", description="atelier — image/video editing webapp")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start the web server")
    start.add_argument("--host", default=None, help="Bind host (default: 0.0.0.0 or ATELIER_HOST)")
    start.add_argument("--port", type=int, default=None, help="Bind port (default: 8000 or ATELIER_PORT)")
    start.add_argument("--reload", action="store_true", help="Enable auto-reload (dev)")

    return parser


def cmd_start(host: str | None, port: int | None, reload: bool) -> None:
    settings = get_settings()
    bind_host = host if host is not None else settings.host
    bind_port = port if port is not None else settings.port
    settings.ensure_data_dir()

    print(f"atelier {__version__} listening on http://{bind_host}:{bind_port}", file=sys.stderr)
    uvicorn.run(
        "atelier.app:create_app",
        factory=True,
        host=bind_host,
        port=bind_port,
        reload=reload,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        cmd_start(host=args.host, port=args.port, reload=args.reload)
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
