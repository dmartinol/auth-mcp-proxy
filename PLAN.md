# Implementation plan

Ordered deliverables for SSO-protected Insights MCP. Research: [AGENTS.md](AGENTS.md#research-read-first).

**Assumptions (confirm before coding):**

- Pilot namespace: `dmartino-insights-mcp-sso`
- Default image registry: **`quay.io/dmartino`**
- Pilot registration mode: **`pre_registered`** + introspection (no Marketplace Handler for v1)
- Upstream MCP image: same as prod `insights-mcp` Deployment
- Implementation language: **Python 3.12** (FastMCP / httpx; aligns with google-lightspeed patterns)

---

## Deliverable 1 — `auth_mcp_proxy` framework (image build & push)

**Outcome:** Runnable container `quay.io/dmartino/auth-mcp-proxy:<tag>` that acts as MCP OAuth resource server + reverse proxy.

### 1.1 Repository scaffold

| Task | Output |
|------|--------|
| Create package layout | `auth_mcp_proxy/` (`main`, `config`, `auth/`, `proxy/`, `metadata/`) |
| Dependencies | `pyproject.toml` or `requirements.txt` — httpx, uvicorn, starlette or `mcp` SDK |
| Config from env | `MCP_*`, `RED_HAT_SSO_*`, `REQUIRED_SCOPES`, `CLIENT_REGISTRATION_MODE`, `LISTEN_*` |
| `.env.example` | Documented vars, no secrets |

### 1.2 Core HTTP server

| Task | Acceptance |
|------|------------|
| Listen on `LISTEN_HOST`:`LISTEN_PORT` | Health: `GET /health`, `GET /ready` → 200 |
| Protected Resource Metadata | `GET /.well-known/oauth-protected-resource` (+ path suffix when `MCP_PUBLIC_URL` has a path) |
| Unauthenticated MCP traffic | `401` + `WWW-Authenticate: Bearer` + `resource_metadata=` PRM URL; optional `scope=` |
| PRM JSON | `resource` = `MCP_PUBLIC_URL`; `authorization_servers` = `[RED_HAT_SSO_ISSUER]`; `scopes_supported` |

Ref: [mcp-oauth-metadata-and-discovery.md](research/mcp-oauth-metadata-and-discovery.md)

### 1.3 Token validation (Red Hat SSO)

| Task | Acceptance |
|------|------------|
| RFC 7662 introspection | POST `{issuer}/protocol/openid-connect/token/introspect` with resource-server Basic auth |
| Reject inactive / missing scope | `401` / `403 insufficient_scope` per [mcp-protocol-authorization.md](research/mcp-protocol-authorization.md) |
| Audience / resource check | Token valid for `MCP_PUBLIC_URL` ([RFC 8707](https://datatracker.ietf.org/doc/html/rfc8707)) |
| `SKIP_JWT_VALIDATION` | Dev-only bypass (never in prod image default) |

Ref: [google-lightspeed-agent-oauth.md](research/google-lightspeed-agent-oauth.md#1-token-introspection-every-a2a-request)

### 1.4 Reverse proxy + Bearer pass-through

| Task | Acceptance |
|------|------------|
| Proxy to `MCP_UPSTREAM_URL` (default `http://127.0.0.1:8080`) | After successful introspection |
| Forward headers | **`Authorization` unchanged**, `Mcp-Session-Id`, `Content-Type`, method/body |
| Do not forward unauthenticated requests | No upstream call without valid Bearer |

Ref: [mcp-protocol-authorization.md](research/mcp-protocol-authorization.md#bearer-pass-through-to-backend-mcp-required)

### 1.5 Registration module (v1 scope)

| Mode | v1 |
|------|-----|
| `pre_registered` | **Yes** — document only; no public `/register` unless needed |
| `rfc7591_dcr` / `cimd` / `rhsso_custom_dcr` | **Defer** — stubs or config flags; no GMA/Marketplace Handler in D1 |

Ref: [mcp-client-oauth-registration.md](research/mcp-client-oauth-registration.md)

### 1.6 Tests

| Task | Output |
|------|--------|
| Unit tests | PRM shape, `401` challenge headers, introspection mock, proxy forwards `Authorization` |
| Optional integration | `pytest` with mock upstream MCP server |

### 1.6a Quality tooling

| Tool | Command |
|------|---------|
| ruff (lint + format) | `make lint`, `make format` |
| mypy | `make typecheck` |
| pytest | `make test` |
| All | `make check` |
| CI | `.github/workflows/ci.yml` on push/PR |

### 1.7 Container build & push

| Item | Value |
|------|--------|
| **Image** | `quay.io/dmartino/auth-mcp-proxy` |
| **Tags** | `:latest`, `:<git-sha>`, `:<version>` (e.g. `0.1.0`) |
| **Containerfile** | UBI or `python:3.12-slim`; non-root user; expose `LISTEN_PORT` |
| **Makefile** (or `scripts/`) | `build`, `push`, `build-push` targets |

```makefile
# Example targets (to implement)
IMAGE ?= quay.io/dmartino/auth-mcp-proxy
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

build:
	podman build -t $(IMAGE):$(TAG) -t $(IMAGE):latest -f Containerfile .

push: build
	podman push $(IMAGE):$(TAG)
	podman push $(IMAGE):latest
```

**D1 done when:**

- [ ] Image pushed to `quay.io/dmartino/auth-mcp-proxy` (at least one tag)
- [ ] Local: unauthenticated → `401` + PRM; valid token (or `SKIP_JWT_VALIDATION`) → upstream receives same Bearer
- [ ] `docs/framework.md` — env table + sidecar fragment for any MCP Deployment

---

## Deliverable 2 — Kubernetes manifests (pilot deployment)

**Outcome:** Parallel stack in pilot NS; prod `tfigenbl-insights-mcp` unchanged.

**Depends on:** D1 image available in Quay (pull secret if namespace requires it).

### 2.1 Layout

```
deploy/k8s/pilot/
├── namespace.yaml
├── configmap-auth-mcp-proxy.yaml
├── secret-auth-mcp-proxy.yaml.example   # not applied from git with real values
├── deployment-auth-insights-mcp.yaml
├── service-auth-insights-mcp.yaml
└── route-auth-insights-mcp.yaml
deploy/k8s/examples/
└── sidecar-container-snippet.yaml        # generic reference from D1 docs
```

### 2.2 Manifest details

| Resource | Spec |
|----------|------|
| **Namespace** | `dmartino-insights-mcp-sso` |
| **Deployment** `auth-insights-mcp` | 2 containers |
| → `auth-mcp-proxy` | Image `quay.io/dmartino/auth-mcp-proxy:<tag>`; port 8443 or 8080; probes `/health` |
| → `insights-mcp` | **Same image as prod**; `127.0.0.1:8080`; **no** `insights-mcp-credentials` volume/env |
| **Service** | Selects sidecar port only |
| **Route** | New host/path; TLS at edge |
| **ConfigMap** | `MCP_PUBLIC_URL` = Route URL; `MCP_UPSTREAM_URL=http://127.0.0.1:8080`; issuer, scopes, `CLIENT_REGISTRATION_MODE=pre_registered` |
| **Secret** | `RED_HAT_SSO_CLIENT_ID`, `RED_HAT_SSO_CLIENT_SECRET` (introspection client) |

### 2.3 Wiring checklist

| Check | |
|-------|---|
| `MCP_PUBLIC_URL` matches Route host + path exactly | |
| PRM well-known path matches public URL path | |
| Service → sidecar, not `insights-mcp` | |
| MCP container not reachable except via localhost | |
| Image pull: `quay.io/dmartino/...` + `imagePullSecrets` if needed | |

### 2.4 Deploy (manual)

1. Create namespace + Secret (from example, out-of-band values).
2. Apply pilot manifests under `deploy/`.
3. Confirm prod `insights-mcp` Route in `tfigenbl-insights-mcp` still works.

### 2.5 Pilot testing guide

Author **[docs/testing.md](docs/testing.md)** — step-by-step verification, not only the short checklist in AGENTS.md.

| Section | Content |
|---------|---------|
| Prerequisites | Pilot URL, SSO client, no prod impact |
| curl smoke | `401`, PRM JSON |
| ocm + Bearer | Token pass-through without MCP UI |
| **Cursor** (primary) | HTTP MCP + OAuth connect + tool call |
| Claude Desktop | `mcp-remote` + pre-registered client |
| Copilot / VS Code | `mcp.json` + pre-registration |
| Gemini Enterprise | Admin UI + fixed redirect URI |
| ChatGPT | Connector OAuth notes |
| Negative tests | Expired token, wrong scope, missing Bearer |
| Troubleshooting | Common failures |

**Recommended pilot client:** Cursor first (fastest loop for developers); add at least one of Claude Desktop or Copilot if stakeholders require it.

**D2 done when:**

- [ ] Pilot Route serves MCP through sidecar only
- [ ] OAuth login + tool call with user token
- [ ] No `insights-mcp-credentials` in pilot Deployment
- [ ] Deploy README under `deploy/` with apply order and SSO prep
- [ ] [docs/testing.md](docs/testing.md) completed; primary path (Cursor) executed successfully on pilot

---

## Suggested PR split

| PR | Scope |
|----|--------|
| **PR1** | D1 — `auth_mcp_proxy`, Containerfile, Makefile, tests, `docs/framework.md`, push to Quay |
| **PR2** | D2 — pilot manifests, deploy README, [docs/testing.md](docs/testing.md) |

---

## Pre-flight (blockers for D2)

Resolve before or during D1:

| Item | Owner |
|------|--------|
| Pilot Route hostname + path (`/` vs `/mcp`) | Platform |
| Red Hat SSO realm URL + introspection client | SSO admin |
| Required scopes (`api.console`, `api.ocm`, …) | SSO admin |
| Prod `insights-mcp` image ref + transport | Cluster |
| Quay repo `dmartino/auth-mcp-proxy` created + push credentials | You |

---

## Out of scope (this plan)

- Production cutover / changing `tfigenbl-insights-mcp`
- Marketplace Handler / `POST /dcr` / GMA (registration-time only; separate service if ever needed)
- Istio / Kuadrant MCP Gateway

---

## Timeline (indicative)

| Phase | Effort |
|-------|--------|
| D1 scaffold + 401/PRM + proxy | 2–3 days |
| D1 introspection + pass-through + tests | 2–3 days |
| D1 Containerfile + Quay push | 0.5 day |
| D2 manifests + pilot smoke | 1–2 days |

Total ~1–2 weeks depending on SSO/pilot environment access.
