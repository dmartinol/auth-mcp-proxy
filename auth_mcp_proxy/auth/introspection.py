"""Red Hat SSO token introspection (RFC 7662)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from auth_mcp_proxy.config import Settings, normalize_resource_url


class AuthError(Exception):
    """Base auth failure."""

    status_code: int = 401
    error: str = "invalid_token"
    description: str = "Invalid or expired token"

    def __init__(
        self,
        description: str | None = None,
        *,
        status_code: int | None = None,
        error: str | None = None,
    ) -> None:
        if description is not None:
            self.description = description
        if status_code is not None:
            self.status_code = status_code
        if error is not None:
            self.error = error
        super().__init__(self.description)


@dataclass(frozen=True)
class TokenInfo:
    active: bool
    scope: str
    client_id: str | None
    sub: str | None


class TokenIntrospector:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._resource = normalize_resource_url(settings.mcp_public_url)

    async def validate_bearer(self, authorization: str | None) -> TokenInfo:
        if self._settings.skip_jwt_validation:
            return TokenInfo(
                active=True,
                scope=self._settings.scope_challenge,
                client_id="dev",
                sub="dev",
            )

        if not authorization or not authorization.lower().startswith("bearer "):
            raise AuthError("Missing or invalid Authorization header")

        token = authorization[7:].strip()
        if not token:
            raise AuthError("Empty bearer token")

        data = await self._introspect(token)
        if not data.get("active"):
            raise AuthError("Token is not active")

        scope = data.get("scope", "")
        if isinstance(scope, list):
            scope = " ".join(scope)

        self._check_scopes(scope)
        self._check_audience(data)

        return TokenInfo(
            active=True,
            scope=scope,
            client_id=data.get("client_id") or data.get("azp"),
            sub=data.get("sub"),
        )

    async def _introspect(self, token: str) -> dict[str, Any]:
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        try:
            response = await client.post(
                self._settings.introspection_url,
                data={"token": token},
                auth=(
                    self._settings.red_hat_sso_client_id,
                    self._settings.red_hat_sso_client_secret,
                ),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        finally:
            if own_client:
                await client.aclose()

        if response.status_code != 200:
            raise AuthError(f"Introspection failed with status {response.status_code}")

        payload: dict[str, Any] = response.json()
        return payload

    def _check_scopes(self, scope: str) -> None:
        granted = set(scope.split())
        missing = [s for s in self._settings.required_scopes if s not in granted]
        if missing:
            raise AuthError(
                f"Insufficient scope; missing: {', '.join(missing)}",
                status_code=403,
                error="insufficient_scope",
            )

    def _check_audience(self, data: dict[str, Any]) -> None:
        aud = data.get("aud")
        if aud is None:
            return
        audiences: list[str]
        if isinstance(aud, list):
            audiences = [str(a) for a in aud]
        else:
            audiences = [str(aud)]

        normalized = {normalize_resource_url(a) for a in audiences}
        if self._resource not in normalized:
            raise AuthError(
                "Token audience does not match this resource server",
                status_code=403,
                error="invalid_token",
            )
