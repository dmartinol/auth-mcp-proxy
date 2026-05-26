# google-lightspeed-agent — OAuth implementation (research)

Reference: [RHEcosystemAppEng/google-lightspeed-agent](https://github.com/RHEcosystemAppEng/google-lightspeed-agent).  
Docs: [authentication.md](https://github.com/RHEcosystemAppEng/google-lightspeed-agent/blob/main/docs/authentication.md), [mcp-integration.md](https://github.com/RHEcosystemAppEng/google-lightspeed-agent/blob/main/docs/mcp-integration.md), [architecture.md](https://github.com/RHEcosystemAppEng/google-lightspeed-agent/blob/main/docs/architecture.md), [marketplace.md](https://github.com/RHEcosystemAppEng/google-lightspeed-agent/blob/main/docs/marketplace.md).

This is **not** standard MCP `registration_endpoint` (RFC 7591). It is a **Google Marketplace + Gemini Enterprise** provisioning flow backed by Red Hat SSO **GMA API**.

---

## Two services, two jobs

| Service | Port | When it runs | OAuth role |
|---------|------|--------------|------------|
| **Marketplace Handler** | 8001 | Always on (provisioning) | **Creates** OAuth clients in Red Hat SSO **once at registration** |
| **Lightspeed Agent** | 8000 | After provisioning | **Validates** tokens (introspection); **forwards** JWT to MCP sidecar |

The agent does **not** implement MCP OAuth discovery (`401` + PRM) for end users. It is an **A2A resource server**, not an MCP resource server.

---

## Marketplace Handler — DCR at registration time

### Why it exists

Gemini Enterprise needs a **dedicated OAuth `client_id` / `client_secret` per marketplace order** before users can obtain tokens from Red Hat SSO. That creation happens **once**, when an admin connects/configures the agent in Gemini—not on each MCP or A2A request.

### Hybrid `POST /dcr` (`marketplace/router.py`)

Single endpoint, two request shapes:

| Path | Trigger | Action |
|------|---------|--------|
| **DCR** | Body contains `software_statement` | Register OAuth client for Gemini |
| **Pub/Sub** | Body contains `message` (base64) | Approve GCP Marketplace account/entitlement; fill DB |

### DCR sequence (registration time only)

```
Admin configures agent in Gemini Enterprise
        │
        ▼
Gemini ──POST /dcr──► Marketplace Handler (8001)
        │              software_statement (JWT signed by Google)
        ▼
1. Validate JWT (Google X.509, aud, exp, google.order, sub)
2. Verify order + account exist in Marketplace PostgreSQL
3. If order already registered → return same client_id/secret (idempotent)
4. Else GMA API → create OAuth tenant client in Red Hat SSO
5. Encrypt secret (Fernet) → store in dcr_clients table
6. Return { client_id, client_secret, client_secret_expires_at: 0 }
        │
        ▼
Gemini stores credentials → later obtains access_token from Red Hat SSO directly
```

**Pub/Sub** (often earlier): Marketplace events approve entitlements and persist orders/accounts so step 2 can succeed. Handler must be deployed **before** the agent ([deployment order](https://github.com/RHEcosystemAppEng/google-lightspeed-agent/blob/main/README.md)).

### GMA API (`dcr/gma_client.py`)

- `POST {realm}/apis/beta/acs/v1/` — create tenant OAuth client
- Handler authenticates to GMA with `GMA_CLIENT_ID` / `GMA_CLIENT_SECRET`, scope `api.iam.clients.gma`
- Client name prefix: `DCR_CLIENT_NAME_PREFIX` (e.g. `gemini-order-`)

### `software_statement` JWT claims

| Claim | Use |
|-------|-----|
| `iss` | Google cert URL for signature verification |
| `aud` | `AGENT_PROVIDER_ORGANIZATION_URL` |
| `sub` | Procurement account ID |
| `google.order` | Order ID — **must exist in DB** |
| `auth_app_redirect_uris` | OAuth redirect URIs for created client |

### Security

- Order must exist in DB (blocks arbitrary Google JWTs).
- Secrets encrypted with `DCR_ENCRYPTION_KEY` (Fernet) before PostgreSQL storage.
- `SKIP_JWT_VALIDATION` for local dev only.

### What the Handler does **not** do

- No user browser login
- No MCP `401` / Protected Resource Metadata
- No token introspection on Insights traffic
- No proxy to `insights-mcp`

---

## Lightspeed Agent — runtime auth

### 1. Token introspection (every A2A request)

- Module: `auth/introspection.py` (RFC 7662)
- POST `{RED_HAT_SSO_ISSUER}/protocol/openid-connect/token/introspect`
- Agent uses **its own** `RED_HAT_SSO_CLIENT_ID` / `SECRET` (resource server), not the DCR-issued client
- Checks: `active`, required scopes (`api.console`, `api.ocm`), allowlist `AGENT_ALLOWED_SCOPES`
- **Why not JWKS?** DCR clients use per-order `client_id` as `aud` → audience mismatch with agent’s client id

Users/clients get tokens **directly from Red Hat SSO** (e.g. `client_credentials`, or `ocm login` for dev)—agent never runs the authorization-code browser flow.

### 2. MCP JWT pass-through (every tool call)

- Module: `tools/mcp_headers.py`
- Injects `Authorization: Bearer <caller JWT>` into HTTP calls to `insights-mcp` sidecar
- MCP container has **no** static Insights credentials; uses forwarded user token for console.redhat.com

```
User token ─► Agent (introspect) ─► MCP sidecar (same Bearer) ─► Insights APIs
```

---

## End-to-end timeline

| Phase | Component | OAuth activity |
|-------|-----------|----------------|
| Marketplace subscribe | Pub/Sub → Handler | Entitlement approved; order in DB |
| **Gemini registration** | **Handler `/dcr`** | **OAuth client created (once per order)** |
| User gets token | Client ↔ Red Hat SSO | Authorization / client_credentials (outside Handler) |
| User chats / tools | Lightspeed Agent | Introspect token |
| Insights data | MCP sidecar | Forward JWT |

---

## Code map

| Path | Responsibility |
|------|----------------|
| `src/lightspeed_agent/marketplace/app.py` | Handler FastAPI app |
| `src/lightspeed_agent/marketplace/router.py` | Hybrid `/dcr` |
| `src/lightspeed_agent/dcr/service.py` | `register_client()` orchestration |
| `src/lightspeed_agent/dcr/gma_client.py` | Red Hat SSO tenant creation |
| `src/lightspeed_agent/dcr/google_jwt.py` | `software_statement` validation |
| `src/lightspeed_agent/dcr/repository.py` | Persist DCR clients |
| `src/lightspeed_agent/auth/introspection.py` | Runtime token validation |
| `src/lightspeed_agent/auth/middleware.py` | Request context for token/user |
| `src/lightspeed_agent/tools/mcp_headers.py` | Bearer forward to MCP |
| `scripts/test_dcr.py` | Local DCR testing |

---

## Configuration (summary)

**Marketplace Handler / DCR**

```bash
GMA_CLIENT_ID=
GMA_CLIENT_SECRET=
DCR_ENCRYPTION_KEY=          # Fernet
DCR_CLIENT_NAME_PREFIX=gemini-order-
# GMA_API_BASE_URL=.../apis/beta/acs/v1/
MARKETPLACE_DATABASE_URL=
```

**Lightspeed Agent (runtime)**

```bash
RED_HAT_SSO_ISSUER=https://sso.redhat.com/auth/realms/redhat-external
RED_HAT_SSO_CLIENT_ID=        # introspection only
RED_HAT_SSO_CLIENT_SECRET=
AGENT_REQUIRED_SCOPE=api.console,api.ocm
AGENT_ALLOWED_SCOPES=openid,profile,email,api.console,api.ocm,metering:admin
MCP_TRANSPORT_MODE=http
MCP_SERVER_URL=http://localhost:8081
SKIP_JWT_VALIDATION=         # dev only
```

---

## Reuse for `sso_authorization` project

| Pattern | Reuse? | Notes |
|---------|--------|-------|
| GMA + `/dcr` for RH SSO client creation | Optional | Only if a **Gemini Marketplace–style** registration service is needed; **not** on MCP connect path |
| **Marketplace Handler as separate service** | Model only | Insights pilot likely uses **pre_registered** clients ([mcp-client-oauth-registration.md](mcp-client-oauth-registration.md)); DCR service optional, not in MCP sidecar hot path |
| Token introspection | **Yes** | Same approach for `auth-mcp-proxy` validating user JWTs |
| JWT pass-through to MCP | **Yes** | Core sidecar behavior |
| Agent as MCP OAuth resource server | **No** | Our sidecar must implement MCP `401`/PRM; lightspeed agent does not |
| Pub/Sub + PostgreSQL marketplace DB | **No** unless building marketplace integration |

**Insights MCP pilot:** user OAuth at **MCP connection** (sidecar) + pass-through to `insights-mcp`. **Do not** require Marketplace Handler unless reproducing Gemini order-based DCR.

---

## Local testing

- DCR: `scripts/test_dcr.py` + Handler with `SKIP_JWT_VALIDATION=true`
- Runtime: `ocm login --use-auth-code` → `ocm token` → A2A `Authorization: Bearer`
- See [README — Testing DCR Locally](https://github.com/RHEcosystemAppEng/google-lightspeed-agent/blob/main/README.md#testing-dcr-locally)
