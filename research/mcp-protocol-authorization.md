# MCP protocol authorization (research)

Quick map of **what the MCP spec requires** for HTTP-based servers—distinct from [metadata/discovery](mcp-oauth-metadata-and-discovery.md), [client registration](mcp-client-oauth-registration.md), and [google-lightspeed-agent](google-lightspeed-agent-oauth.md) (A2A, not MCP).

**Canonical spec:** [MCP Authorization (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)  
**Tutorial:** [Understanding Authorization in MCP](https://modelcontextprotocol.io/docs/tutorials/security/authorization)

---

## When it applies

| Transport | MCP OAuth spec? |
|-----------|-------------------|
| **HTTP** (Streamable HTTP, SSE) | **Yes** — our pilot (Route → sidecar) |
| **stdio** | **No** — credentials from env / local tools; not Red Hat SSO browser flow |

Authorization is **optional** in MCP, but remote Insights MCP over HTTP **should** conform if we require user login.

---

## Roles (OAuth 2.1)

```
┌─────────────┐     Bearer token      ┌──────────────────┐     introspect/JWKS   ┌─────────────┐
│ MCP client  │ ────────────────────► │ MCP server       │ ──────────────────► │ Red Hat SSO │
│ (Cursor,    │                     │ (auth-mcp-proxy) │                     │ (AuthZ AS)  │
│  ChatGPT…)  │ ◄── MCP JSON-RPC ── │  resource server │                     │             │
└─────────────┘                     └────────┬─────────┘                     └─────────────┘
                                           │ proxy (authenticated)
                                           ▼
                                    ┌──────────────────┐
                                    │ insights-mcp       │
                                    │ (no OAuth surface) │
                                    └──────────────────┘
```

- **Resource server** = sidecar at public URL. Must publish PRM and **validate every request’s access token** before proxying.
- **Authorization server** = Red Hat SSO. User login, token issue, optional registration.
- **MCP client** = obtains token from SSO, sends `Authorization: Bearer` on MCP HTTP calls.

The spec does **not** require the resource server to run `/authorize` or `/token`—only to **discover** the AS and **validate** tokens.

---

## Protocol-level flow

1. Client sends MCP HTTP request **without** token (or with invalid token).
2. Resource server returns **`401 Unauthorized`** with `WWW-Authenticate: Bearer` and preferably `resource_metadata=<PRM URL>` (and optional `scope=`).
3. Client loads **Protected Resource Metadata** (RFC 9728) from MCP host.
4. Client discovers AS metadata from `authorization_servers[]` (RFC 8414 / OIDC).
5. Client registers (pre-reg / CIMD / DCR) if needed — see [mcp-client-oauth-registration.md](mcp-client-oauth-registration.md).
6. User completes **authorization code + PKCE** at SSO.
7. Client retries MCP requests with **`Authorization: Bearer <access_token>`**.
8. Resource server validates token → forwards to upstream MCP.

OAuth happens **between client and SSO**. MCP messages after step 7 are normal JSON-RPC (initialize, tools/list, tools/call) over authenticated HTTP.

---

## Token rules (resource server MUST)

| Rule | Implication for sidecar |
|------|-------------------------|
| Token in **`Authorization: Bearer` only** | Never accept `?token=` or API keys in URL ([spec token requirements](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#token-requirements)) |
| **No tokens in query string** | Reject or strip if present |
| Validate token before MCP handling | Return `401` if missing/invalid/inactive |
| **Audience / resource indicator** ([RFC 8707](https://datatracker.ietf.org/doc/html/rfc8707)) | Token must be issued **for this MCP server URL** (`MCP_PUBLIC_URL` / `resource` in PRM) |
| Only accept tokens from **this** AS | Reject tokens minted for other APIs |
| **`401`** for invalid/expired; **`403`** + `insufficient_scope` for valid token, wrong scopes | Map introspection scope checks accordingly |

Clients should send `resource` (or equivalent) when requesting tokens from SSO so `aud` matches the MCP URL.

---

## What the sidecar implements (MCP layer)

| Responsibility | Detail |
|----------------|--------|
| Act as OAuth **resource server** | Not full AS |
| `401` + `WWW-Authenticate` | Include `resource_metadata`; optional `scope` aligned with `scopes_supported` |
| Serve PRM | See [mcp-oauth-metadata-and-discovery.md](mcp-oauth-metadata-and-discovery.md) |
| Validate Bearer on **all** protected MCP methods | Including `GET`/`POST`/`DELETE` used by Streamable HTTP and session endpoints |
| Pass through after auth | `Authorization`, `Mcp-Session-Id`, body unchanged to `insights-mcp` |
| Do **not** treat `Mcp-Session-Id` as identity | Session is transport state; auth = Bearer only ([security best practices](https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices)) |

---

## Bearer pass-through to backend MCP (required)

After the sidecar validates the token, it **must forward the same** `Authorization: Bearer <access_token>` **header** to `insights-mcp` on every proxied request (initialize, tools, SSE/session traffic).

| Step | Component |
|------|-----------|
| 1 | Client → sidecar: Bearer (user token from Red Hat SSO) |
| 2 | Sidecar: introspect / validate scopes & audience |
| 3 | Sidecar → `insights-mcp` (loopback): **same Bearer unchanged** |
| 4 | `insights-mcp` → console.redhat.com: uses that JWT as the end user |

This replaces `insights-mcp-credentials`: the backend must **not** rely on a static Secret for user-scoped Insights APIs.

Reference: google-lightspeed `tools/mcp_headers.py` ([google-lightspeed-agent-oauth.md](google-lightspeed-agent-oauth.md#2-mcp-jwt-pass-through-every-tool-call)). Pilot test: tool call succeeds with credentials Secret removed from the MCP container.

**Do not** strip `Authorization` at the proxy. **Do not** substitute the sidecar’s introspection client credentials for the user token on upstream requests.

---

## What stays on insights-mcp (upstream)

- MCP tool implementations, JSON-RPC semantics.
- Trusts the sidecar to only forward already-validated requests; calls Insights APIs with the **caller's** Bearer.
- No requirement to implement PRM or `401` on the loopback port if only reachable from sidecar.

---

## Transport notes (HTTP auth vs MCP messages)

| Concern | Auth interaction |
|---------|------------------|
| **Streamable HTTP** | Primary; auth is per HTTP request |
| **SSE** | Same Bearer on HTTP layer if used |
| **`Mcp-Session-Id`** | Opaque session key after `initialize`; still send Bearer on each request |
| **Initialize** | First call may trigger `401` → full OAuth dance, then `initialize` with token |

**Open point for pilot:** confirm prod `insights-mcp` uses Streamable HTTP path and whether SSE is enabled — affects which HTTP methods the sidecar must protect ([metadata doc checklist](mcp-oauth-metadata-and-discovery.md)).

---

## Standards stack (subset MCP uses)

- OAuth 2.1 (draft) — authorization code, PKCE
- RFC 9728 — Protected Resource Metadata
- RFC 8414 / OIDC Discovery — AS metadata
- RFC 8707 — Resource Indicators (`resource` parameter)
- RFC 7662 — introspection (our validation approach; spec allows validation libraries)
- RFC 7591 / CIMD draft — registration (optional per client)

---

## Gaps vs other research docs

| Topic | Covered in |
|-------|------------|
| `.well-known` URLs on MCP vs SSO | [mcp-oauth-metadata-and-discovery.md](mcp-oauth-metadata-and-discovery.md) |
| ChatGPT / Copilot / GE / Claude registration | [mcp-client-oauth-registration.md](mcp-client-oauth-registration.md) |
| Marketplace `/dcr`, introspection, JWT to MCP | [google-lightspeed-agent-oauth.md](google-lightspeed-agent-oauth.md) |
| **Spec roles, token rules, 401/403, transport** | **this doc** |

---

## Pre-development checks (MCP protocol)

- [ ] Unauthenticated MCP `POST`/`GET` to pilot URL returns **401** (not 200 with error in JSON-RPC body).
- [ ] Authenticated requests use **header only** for token.
- [ ] After OAuth, same **Route URL** used in PRM `resource` and token `aud` / resource indicator.
- [ ] Sidecar rejects upstream exposure without Bearer (MCP bound to localhost).
- [ ] Scope challenge in `401` matches Insights needs (`api.console`, `api.ocm` or realm-specific).

---

## Verdict: do we need this research?

**Yes, briefly.** Metadata research answers *where* to host discovery documents; client research answers *how clients register*; this doc answers **what the MCP resource server must do on each HTTP request** and how that differs from A2A/google-lightspeed.

Enough to plan `auth-mcp-proxy` middleware order: **HTTP auth gate → PRM routes → reverse proxy → insights-mcp**.
