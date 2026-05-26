"""Starlette application: PRM, auth gate, MCP reverse proxy."""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from auth_mcp_proxy.auth import (
    AuthError,
    TokenIntrospector,
    build_prm_document,
    www_authenticate_header,
)
from auth_mcp_proxy.config import Settings, load_settings, prm_well_known_urls
from auth_mcp_proxy.proxy import proxy_request

# MCP and HTTP transports use POST; SSE may use GET.
_MCP_METHODS = ["GET", "POST", "DELETE", "OPTIONS", "HEAD"]


async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def ready(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ready")


def _auth_error_response(settings: Settings, exc: AuthError) -> JSONResponse:
    headers: dict[str, str] = {}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = www_authenticate_header(settings)
    return JSONResponse(
        {"error": exc.error, "error_description": exc.description},
        status_code=exc.status_code,
        headers=headers,
    )


def create_app(settings: Settings | None = None) -> Starlette:
    cfg = settings or load_settings()
    introspector = TokenIntrospector(cfg)
    valid_prm_paths = {urlparse(url).path for url in prm_well_known_urls(cfg.mcp_public_url)}

    async def prm_handler(request: Request) -> Response:
        if request.url.path not in valid_prm_paths:
            return PlainTextResponse("Not Found", status_code=404)
        return JSONResponse(build_prm_document(cfg))

    async def protected_handler(request: Request) -> Response:
        try:
            await introspector.validate_bearer(request.headers.get("authorization"))
        except AuthError as exc:
            return _auth_error_response(cfg, exc)
        return await proxy_request(request, cfg.mcp_upstream_url)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/ready", ready, methods=["GET"]),
        Route(
            "/.well-known/oauth-protected-resource",
            prm_handler,
            methods=["GET"],
        ),
        Route(
            "/.well-known/oauth-protected-resource/{resource_path:path}",
            prm_handler,
            methods=["GET"],
        ),
        Route("/", protected_handler, methods=_MCP_METHODS),
        Route("/{path:path}", protected_handler, methods=_MCP_METHODS),
    ]

    return Starlette(routes=routes)
