"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).lower()
    return raw in ("1", "true", "yes", "on")


def _list_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default).strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass(frozen=True)
class Settings:
    listen_host: str
    listen_port: int
    mcp_upstream_url: str
    mcp_public_url: str
    red_hat_sso_issuer: str
    red_hat_sso_client_id: str
    red_hat_sso_client_secret: str
    required_scopes: list[str]
    client_registration_mode: str
    skip_jwt_validation: bool
    log_level: str

    @property
    def introspection_url(self) -> str:
        base = self.red_hat_sso_issuer.rstrip("/") + "/"
        return urljoin(base, "protocol/openid-connect/token/introspect")

    @property
    def prm_document_url(self) -> str:
        """Primary PRM URL for WWW-Authenticate resource_metadata."""
        urls = prm_well_known_urls(self.mcp_public_url)
        return urls[0]

    @property
    def scope_challenge(self) -> str:
        return " ".join(self.required_scopes)


def prm_well_known_urls(public_url: str) -> list[str]:
    """Well-known PRM URLs (most specific path first)."""
    parsed = urlparse(public_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls: list[str] = []
    path = parsed.path.strip("/")
    if path:
        urls.append(f"{base}/.well-known/oauth-protected-resource/{path}")
    urls.append(f"{base}/.well-known/oauth-protected-resource")
    return urls


def load_settings() -> Settings:
    issuer = os.getenv("RED_HAT_SSO_ISSUER", "https://sso.redhat.com/auth/realms/redhat-external")
    public = os.getenv("MCP_PUBLIC_URL", "http://localhost:8080")
    return Settings(
        listen_host=os.getenv("LISTEN_HOST", "0.0.0.0"),
        listen_port=int(os.getenv("LISTEN_PORT", "8080")),
        mcp_upstream_url=os.getenv("MCP_UPSTREAM_URL", "http://127.0.0.1:8080"),
        mcp_public_url=public,
        red_hat_sso_issuer=issuer,
        red_hat_sso_client_id=os.getenv("RED_HAT_SSO_CLIENT_ID", ""),
        red_hat_sso_client_secret=os.getenv("RED_HAT_SSO_CLIENT_SECRET", ""),
        required_scopes=_list_env("REQUIRED_SCOPES", "api.console,api.ocm"),
        client_registration_mode=os.getenv("CLIENT_REGISTRATION_MODE", "pre_registered"),
        skip_jwt_validation=_bool_env("SKIP_JWT_VALIDATION"),
        log_level=os.getenv("LOG_LEVEL", "info"),
    )


def normalize_resource_url(url: str) -> str:
    """Normalize URL for audience comparison (no trailing slash on path-only roots)."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or ""
    if path:
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    return f"{parsed.scheme}://{parsed.netloc}"
