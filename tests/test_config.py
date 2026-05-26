from auth_mcp_proxy.config import normalize_resource_url, prm_well_known_urls


def test_prm_well_known_urls_with_path() -> None:
    urls = prm_well_known_urls("https://host.example/mcp")
    assert urls[0] == "https://host.example/.well-known/oauth-protected-resource/mcp"
    assert urls[1] == "https://host.example/.well-known/oauth-protected-resource"


def test_normalize_resource_url() -> None:
    assert normalize_resource_url("https://host/mcp/") == "https://host/mcp"
    assert normalize_resource_url("https://host") == "https://host"
