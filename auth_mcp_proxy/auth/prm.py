"""Protected Resource Metadata (RFC 9728)."""

from __future__ import annotations

from typing import Any

from auth_mcp_proxy.config import Settings


def build_prm_document(settings: Settings) -> dict[str, Any]:
    return {
        "resource": settings.mcp_public_url,
        "authorization_servers": [settings.red_hat_sso_issuer.rstrip("/")],
        "scopes_supported": settings.required_scopes,
    }


def www_authenticate_header(settings: Settings) -> str:
    parts = [
        'Bearer realm="mcp"',
        f'resource_metadata="{settings.prm_document_url}"',
    ]
    if settings.required_scopes:
        parts.append(f'scope="{settings.scope_challenge}"')
    return ", ".join(parts)
