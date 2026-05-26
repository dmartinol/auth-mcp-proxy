# SSO Authorization for Insights MCP

Agent instructions for a **reusable MCP OAuth framework** (Red Hat SSO) and a **parallel pilot deployment** of Insights MCP—without changing production initially.

## Mission

Replace embedded service-account credentials (`insights-mcp-credentials`) with **per-user OAuth** via Red Hat SSO. MCP clients complete the [MCP authorization flow](https://modelcontextprotocol.io/docs/tutorials/security/authorization) (browser login → JWT on all MCP traffic).

| # | Requirement | Outcome |
|---|-------------|---------|
| **1** | **Reusable SSO framework** | Sidecar + config contract for any HTTP MCP backend. |
| **2** | **Pilot deployment** | Parallel `auth-insights-mcp` in a **separate namespace**; prove E2E before prod cutover. |

**Do not** modify `insights-mcp` in `tfigenbl-insights-mcp` until the pilot passes.

---

## Research (read first)

| Doc | Contents |
|-----|----------|
| [research/google-lightspeed-agent-oauth.md](research/google-lightspeed-agent-oauth.md) | Reference OAuth: **Marketplace Handler** (one-time DCR via GMA), introspection, MCP JWT pass-through |
| [research/mcp-client-oauth-registration.md](research/mcp-client-oauth-registration.md) | Target clients (ChatGPT, Copilot Ent., Gemini Ent., Claude Desktop), CIMD vs DCR vs pre-registration |
| [research/mcp-oauth-metadata-and-discovery.md](research/mcp-oauth-metadata-and-discovery.md) | **Which `.well-known` URLs** on sidecar vs Red Hat SSO; other pre-dev checklist |
| [research/mcp-protocol-authorization.md](research/mcp-protocol-authorization.md) | **MCP spec** roles, 401/403, Bearer rules, transport vs OAuth (HTTP only) |

---

## Requirement 1 — Reusable SSO framework

### Goal

Build **`auth-mcp-proxy`**: MCP resource server + reverse proxy to a configurable upstream.

- MCP `401` + `WWW-Authenticate` + Protected Resource Metadata (RFC 9728)
- Red Hat SSO token validation (introspection RFC 7662; pattern from [google-lightspeed-agent](research/google-lightspeed-agent-oauth.md))
- **Configurable client registration** — see [mcp-client-oauth-registration.md](research/mcp-client-oauth-registration.md)
- Optional **RH custom `/dcr` + GMA** — registration-time only, like Marketplace Handler; not required for Insights pilot
- Validate Bearer at sidecar, then **forward the same Bearer** to upstream MCP (replaces `insights-mcp-credentials`; see [mcp-protocol-authorization.md](research/mcp-protocol-authorization.md#bearer-pass-through-to-backend-mcp-required))

Insights MCP is the first consumer, not the only one.

### Target MCP clients

ChatGPT, **Copilot Enterprise**, **Gemini Enterprise**, **Claude Desktop** — registration paths differ; see research doc.

### Framework boundaries

**In scope:** HTTP/SSE proxy, PRM/metadata, Bearer validation, pluggable registration modes, health probes, env/ConfigMap config.

**Out of scope:** Insights tool semantics, forking `insights-mcp`, Istio/Kuadrant [MCP Gateway](https://github.com/Kuadrant/mcp-gateway/blob/main/VISION.md), prod cutover, Gemini Pub/Sub marketplace (unless explicitly requested).

### Implementation phases

1. Skeleton — proxy, health, unauthenticated → `401` + challenge.
2. MCP metadata — PRM + `401` challenge ([well-known research](research/mcp-oauth-metadata-and-discovery.md)); `MCP_PUBLIC_URL` for resource/audience.
3. Red Hat SSO — introspection, scopes (e.g. `api.console`, `api.ocm`).
4. Registration module — `CLIENT_REGISTRATION_MODE` per [mcp-client-oauth-registration.md](research/mcp-client-oauth-registration.md); optional `rhsso_custom_dcr` per [google-lightspeed-agent-oauth.md](research/google-lightspeed-agent-oauth.md).
5. Proxy hardening — headers, timeouts, loopback upstream.

### Configuration contract (high level)

| Variable | Purpose |
|----------|---------|
| `MCP_UPSTREAM_URL`, `MCP_PUBLIC_URL` | Upstream + external URL |
| `RED_HAT_SSO_ISSUER`, `RED_HAT_SSO_CLIENT_ID`, `RED_HAT_SSO_CLIENT_SECRET` | Introspection (resource server) |
| `REQUIRED_SCOPES`, `CLIENT_REGISTRATION_MODE`, `PRE_REGISTERED_CLIENTS` | AuthZ + registration |
| `GMA_*`, `DCR_ENCRYPTION_KEY` | Only if `rhsso_custom_dcr` / Marketplace-style DCR service |

Full env tables and GMA/DCR flow: [google-lightspeed-agent-oauth.md](research/google-lightspeed-agent-oauth.md).

### Deliverables

Python sidecar source, container build, automated tests and quality checks, framework documentation, and example Kubernetes fragments under `deploy/`.

---

## Requirement 2 — Pilot: parallel Insights MCP

### Goal

Deploy **auth-insights-mcp** in a **new namespace** (`dmartino-insights-mcp-sso`). Production `tfigenbl-insights-mcp` unchanged.

| Resource | Pilot NS |
|----------|----------|
| Deployment `auth-insights-mcp` | `auth-mcp-proxy` + `insights-mcp` (no `insights-mcp-credentials`) |
| Service / Route | New hostname; `MCP_PUBLIC_URL` = pilot Route only |

### Runtime flow (pilot)

MCP spec OAuth at sidecar → user JWT → validate → proxy to `insights-mcp` with same Bearer ([pass-through pattern](research/google-lightspeed-agent-oauth.md#2-mcp-jwt-pass-through-every-tool-call)).

**Not** the google-lightspeed **Marketplace Handler** path unless you add a separate registration service for Gemini-style `/dcr`.

### Manifests

OpenShift/Kubernetes resources for the pilot stack under `deploy/` (namespace, dual-container deployment, service, route, config, secret templates). Verify with [docs/testing.md](docs/testing.md). See [PLAN.md](PLAN.md) for deliverable order.

### Pilot checklist

Short list; full steps (curl, **Cursor**, Claude Desktop, Copilot, Gemini, ChatGPT): **[docs/testing.md](docs/testing.md)**.

1. Prod route unchanged.
2. Pilot → `401` + valid PRM when unauthenticated.
3. OAuth via Red Hat SSO from MCP client (primary: **Cursor** — see testing guide).
4. Tool call works; sidecar forwards unchanged `Authorization: Bearer` to `insights-mcp` (no static Insights creds in pod).
5. Negative: bad `aud`, missing scope, expired token.
6. Optional: manual Bearer via `ocm login` + `ocm token` (testing guide §2).

---

## Shared constraints

- Sidecar + localhost upstream; plain K8s YAML.
- Keep upstream `insights-mcp` image.
- No Istio/MCP Gateway requirement; no prod NS edits during pilot; no secrets in git.

---

## Repository layout

| Area | Purpose |
|------|---------|
| **Agent & plan docs** | `AGENTS.md`, [PLAN.md](PLAN.md) — scope and sequencing |
| **`research/`** | Background notes (OAuth reference impl, MCP spec, client registration, metadata) — index in [Research](#research-read-first) |
| **Sidecar implementation** | `auth_mcp_proxy/` — proxy, auth, packaging, CI |
| **`deploy/`** | Pilot and example cluster manifests |
| **`docs/`** | Framework guide + **[pilot testing](docs/testing.md)** (Cursor, Claude Desktop, Copilot, curl, ocm) |

**Implementation plan:** [PLAN.md](PLAN.md) — Deliverable 1: sidecar image (`quay.io/dmartino/auth-mcp-proxy`); Deliverable 2: pilot manifests under `deploy/`.

**Sequencing:** D1 image → D2 manifests → pilot acceptance → optional prod migration.

---

## Agent working agreements

1. Separate PRs for framework vs pilot when possible.
2. Pilot `MCP_PUBLIC_URL` ≠ prod Route.
3. Distinguish **registration-time DCR** (Handler/GMA) from **runtime MCP OAuth** (sidecar)—see research.
4. Do not commit unless the user asks.

---

## Key references

- [MCP Authorization tutorial](https://modelcontextprotocol.io/docs/tutorials/security/authorization)
- [google-lightspeed-agent](https://github.com/RHEcosystemAppEng/google-lightspeed-agent)
- [insights-mcp](https://github.com/RedHatInsights/insights-mcp)

---

## Open questions

See also pre-development checklist in [mcp-oauth-metadata-and-discovery.md](research/mcp-oauth-metadata-and-discovery.md).

- `auth-mcp-proxy` language (Go vs Python).
- Pilot namespace, Route host, SSO realm, scopes, MCP path (`/` vs `/mcp`).
- Whether Insights pilot needs any `rhsso_custom_dcr` service or only `pre_registered` + introspection.
