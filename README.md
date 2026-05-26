# SSO authorization for Insights MCP

OAuth-protected MCP access via a sidecar (`auth-mcp-proxy`) and Red Hat SSO.

- Agent instructions: [AGENTS.md](AGENTS.md)
- Implementation plan: [PLAN.md](PLAN.md)
- Pilot testing: [docs/testing.md](docs/testing.md)

## Quick start (local)

```bash
make install
make check
i
# Dev: no SSO introspection (any Bearer accepted)
make run

# Real JWT validation via Red Hat SSO introspection
cp .env.example .env   # set RED_HAT_SSO_CLIENT_ID / RED_HAT_SSO_CLIENT_SECRET
set -a && source .env && set +a
make run-auth
```

Test with a user token: `ocm login --use-auth-code`, then `curl ... -H "Authorization: Bearer $(ocm token)"` to `http://localhost:8080/mcp`.

Container image: `quay.io/dmartino/auth-mcp-proxy`

```bash
make build
make push   # requires Quay credentials
```
