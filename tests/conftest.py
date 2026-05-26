import pytest

from auth_mcp_proxy.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        listen_host="127.0.0.1",
        listen_port=18080,
        mcp_upstream_url="http://127.0.0.1:19999",
        mcp_public_url="https://mcp.example.com/mcp",
        red_hat_sso_issuer="https://sso.example.com/auth/realms/test",
        red_hat_sso_client_id="introspect-client",
        red_hat_sso_client_secret="secret",
        required_scopes=["api.console", "api.ocm"],
        client_registration_mode="pre_registered",
        skip_jwt_validation=True,
        log_level="warning",
    )
