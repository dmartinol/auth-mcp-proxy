"""Reverse proxy to upstream MCP with header pass-through."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response

# MCP Streamable HTTP clients must send this; curl often omits it → upstream 406.
_DEFAULT_MCP_ACCEPT = "application/json, text/event-stream"

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _is_mcp_path(path: str) -> bool:
    normalized = (path or "/").rstrip("/")
    return normalized == "/mcp" or normalized.endswith("/mcp")


def _ensure_streamable_http_accept(headers: dict[str, str]) -> None:
    """FastMCP / insights-mcp return 406 unless both JSON and SSE are accepted."""
    accept = ""
    for key in list(headers):
        if key.lower() == "accept":
            accept = headers.pop(key)
            break
    lower = accept.lower()
    if "application/json" in lower and "text/event-stream" in lower:
        headers["Accept"] = accept
    else:
        headers["Accept"] = _DEFAULT_MCP_ACCEPT


def _forward_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP or lower == "host":
            continue
        out[key] = value
    if _is_mcp_path(request.url.path):
        _ensure_streamable_http_accept(out)
    return out


async def proxy_request(request: Request, upstream_base: str) -> Response:
    """Forward the incoming request to upstream, preserving Authorization and MCP headers."""
    upstream = upstream_base.rstrip("/")
    path = request.url.path or "/"
    query = request.url.query
    url = f"{upstream}{path}"
    if query:
        url = f"{url}?{query}"

    headers = _forward_request_headers(request)
    body = await request.body()

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        upstream_resp = await client.request(
            request.method,
            url,
            headers=headers,
            content=body if body else None,
        )

    response_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in HOP_BY_HOP
    }

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=response_headers,
    )
