from dataclasses import replace

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from auth_mcp_proxy.app import create_app
from auth_mcp_proxy.auth.introspection import AuthError, TokenIntrospector
from auth_mcp_proxy.auth.prm import build_prm_document, www_authenticate_header
from auth_mcp_proxy.config import Settings


def test_build_prm_document(test_settings: Settings) -> None:
    doc = build_prm_document(test_settings)
    assert doc["resource"] == test_settings.mcp_public_url
    assert test_settings.red_hat_sso_issuer.rstrip("/") in doc["authorization_servers"][0]
    assert "api.console" in doc["scopes_supported"]


def test_www_authenticate_includes_resource_metadata(test_settings: Settings) -> None:
    header = www_authenticate_header(test_settings)
    assert "Bearer" in header
    assert "resource_metadata=" in header
    assert test_settings.prm_document_url in header


def test_unauthenticated_returns_401(test_settings: Settings) -> None:
    settings = replace(test_settings, skip_jwt_validation=False)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "resource_metadata" in response.headers["WWW-Authenticate"]


def test_prm_endpoint(test_settings: Settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    assert response.json()["resource"] == test_settings.mcp_public_url


@respx.mock
@pytest.mark.asyncio
async def test_introspection_validates_scopes(test_settings: Settings) -> None:
    settings = replace(test_settings, skip_jwt_validation=False)
    respx.post(settings.introspection_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "active": True,
                "scope": "api.console",
                "client_id": "user-client",
                "sub": "user-1",
                "aud": settings.mcp_public_url,
            },
        )
    )
    introspector = TokenIntrospector(settings)
    with pytest.raises(AuthError) as exc:
        await introspector.validate_bearer("Bearer token")
    assert exc.value.status_code == 403

    respx.post(settings.introspection_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "active": True,
                "scope": "api.console api.ocm",
                "aud": settings.mcp_public_url,
            },
        )
    )
    info = await introspector.validate_bearer("Bearer good-token")
    assert info.active


@respx.mock
def test_proxy_forwards_authorization(test_settings: Settings) -> None:
    upstream = test_settings.mcp_upstream_url.rstrip("/")

    def upstream_route(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer user-jwt"
        return httpx.Response(200, json={"ok": True})

    respx.post(f"{upstream}/").mock(side_effect=upstream_route)

    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/",
            headers={"Authorization": "Bearer user-jwt"},
            json={"jsonrpc": "2.0", "id": 1},
        )
    assert response.status_code == 200


@respx.mock
def test_proxy_normalizes_accept_on_mcp_path(test_settings: Settings) -> None:
    upstream = test_settings.mcp_upstream_url.rstrip("/")

    def upstream_route(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("accept") == "application/json, text/event-stream"
        return httpx.Response(200, json={"ok": True})

    respx.post(f"{upstream}/mcp").mock(side_effect=upstream_route)

    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer user-jwt", "Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 1},
        )
    assert response.status_code == 200
