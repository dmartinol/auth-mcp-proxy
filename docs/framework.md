# auth-mcp-proxy framework

Sidecar that implements the MCP **resource server** role: RFC 9728 Protected Resource Metadata, `401` challenges, Red Hat SSO token introspection, and reverse proxy to a co-located upstream MCP with the **same** `Authorization: Bearer` header.

## Architecture

```
MCP client → Route → auth-mcp-proxy → insights-mcp (127.0.0.1) → console.redhat.com
```

The sidecar does **not** expose SSO `/authorize` or `/token`; clients discover the authorization server from PRM and talk to Red Hat SSO directly.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LISTEN_HOST` | No | `0.0.0.0` | Bind address |
| `LISTEN_PORT` | No | `8080` | Bind port |
| `MCP_PUBLIC_URL` | Yes (prod) | `http://localhost:8080` | Public MCP URL (Route); used in PRM `resource` and audience checks |
| `MCP_UPSTREAM_URL` | No | `http://127.0.0.1:8080` | Loopback upstream MCP in the same pod |
| `RED_HAT_SSO_ISSUER` | Yes (prod) | `https://sso.redhat.com/auth/realms/redhat-external` | Issuer in PRM `authorization_servers` |
| `RED_HAT_SSO_CLIENT_ID` | Yes (prod) | — | Introspection client (resource server) |
| `RED_HAT_SSO_CLIENT_SECRET` | Yes (prod) | — | Introspection client secret |
| `REQUIRED_SCOPES` | No | `api.console,api.ocm` | Comma-separated scopes; enforced after introspection |
| `CLIENT_REGISTRATION_MODE` | No | `pre_registered` | v1: document only (`pre_registered`) |
| `SKIP_JWT_VALIDATION` | No | `false` | Dev bypass; **never** in production |
| `LOG_LEVEL` | No | `info` | Logging level |

Introspection endpoint is derived: `{RED_HAT_SSO_ISSUER}/protocol/openid-connect/token/introspect`.

## HTTP surface

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | No | Liveness |
| `GET /ready` | No | Readiness |
| `GET /.well-known/oauth-protected-resource` | No | PRM (root) |
| `GET /.well-known/oauth-protected-resource/{path}` | No | PRM when `MCP_PUBLIC_URL` has a path segment |
| `*` (MCP traffic) | Bearer | Introspect then proxy to upstream |

Unauthenticated MCP requests receive `401` with:

```
WWW-Authenticate: Bearer realm="mcp", resource_metadata="<PRM URL>", scope="..."
```

## Sidecar container (Kubernetes)

See [deploy/k8s/examples/sidecar-container-snippet.yaml](../deploy/k8s/examples/sidecar-container-snippet.yaml).

Key wiring:

- Service and Route target the **sidecar** port only.
- `MCP_UPSTREAM_URL=http://127.0.0.1:8080` (or the port `insights-mcp` listens on).
- `MCP_PUBLIC_URL` must match the Route URL **exactly** (scheme, host, path).
- Mount introspection credentials from a Secret; do not bake secrets into the image.

## Image

`quay.io/dmartino/auth-mcp-proxy`

```bash
make build
make push
```

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
SKIP_JWT_VALIDATION=true MCP_PUBLIC_URL=http://localhost:8080 auth-mcp-proxy
```

## Registration (v1)

`CLIENT_REGISTRATION_MODE=pre_registered`: register MCP clients in Red Hat SSO admin UI (or enterprise admin consoles). No public DCR endpoint on the sidecar in v1.
