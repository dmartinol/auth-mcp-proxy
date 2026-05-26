"""CLI entrypoint."""

from __future__ import annotations

import logging

import uvicorn

from auth_mcp_proxy.app import create_app
from auth_mcp_proxy.config import load_settings


def run() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.listen_host,
        port=settings.listen_port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    run()
