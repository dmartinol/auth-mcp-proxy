# MCP OAuth metadata & discovery (research)

What must be exposed **where** before implementing `auth-mcp-proxy`.  
Spec: [MCP Authorization 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization), [RFC 9728 PRM](https://datatracker.ietf.org/doc/html/rfc9728), [RFC 8414 AS metadata](https://datatracker.ietf.org/doc/html/rfc8414).

---

## Two hosts, two roles

| Role | Who | Typical host |
|------|-----|----------------|
| **Resource server (MCP)** | `auth-mcp-proxy` | Pilot Route, e.g. `https://insights-mcp-sso.example.com` |
| **Authorization server** | Red Hat SSO (Keycloak) | e.g. `https://sso.redhat.com/auth/realms/redhat-external` |

Do **not** re-implement authorize/token on the MCP host unless building a full OAuth gateway. The sidecar publishes **Protected Resource Metadata** and validates tokens; users log in at **Red Hat SSO**.

google-lightspeed-agent exposes **neither** MCP PRM nor AS metadata on the agent—it is A2A-only. Our framework **must** implement PRM on the sidecar.

---

## On the MCP host (sidecar) — required

### 1. Protected Resource Metadata (RFC 9728) — **implement**

Clients need a JSON document listing the resource URL and which authorization server(s) to use.

**URLs** (MCP spec; clients try in order if `401` lacks `resource_metadata`):

| MCP public URL | PRM URL (path insertion) | PRM URL (root fallback) |
|----------------|--------------------------|-------------------------|
| `https://host/` | `https://host/.well-known/oauth-protected-resource` | same |
| `https://host/mcp` | `https://host/.well-known/oauth-protected-resource/mcp` | `https://host/.well-known/oauth-protected-resource` |

**Recommendation:** Set `MCP_PUBLIC_URL` to the **exact** URL clients use (including path). Serve PRM at the matching well-known path **and** return the same URL in `401`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="mcp",
  resource_metadata="https://<MCP_PUBLIC_HOST>/.well-known/oauth-protected-resource[/mcp]"
```

Claude treats `resource_metadata` on `401` as the **most reliable** discovery path ([Claude connector auth](https://claude.com/docs/connectors/building/authentication)).

**Example PRM body:**

```json
{
  "resource": "https://insights-mcp-sso.example.com/mcp",
  "authorization_servers": ["https://sso.redhat.com/auth/realms/redhat-external"],
  "scopes_supported": ["api.console", "api.ocm"]
}
```

- `resource` must **exactly** match how the client registers the server URL.
- `authorization_servers[0]` is the SSO **issuer** (first entry is used by Claude).
- `scopes_supported` guides client scope requests; align with `REQUIRED_SCOPES`.

### 2. MCP protocol routes — **proxy**

- Streamable HTTP (and SSE if used): same path clients hit today on `insights-mcp`.
- Pass-through: `Authorization`, `Mcp-Session-Id`, `Content-Type`.

### 3. Health — **implement**

- `/health`, `/ready` (not part of OAuth; for K8s probes).

### 4. Optional on MCP host (by registration mode)

| Endpoint | When | Notes |
|----------|------|-------|
| `POST /register` | `CLIENT_REGISTRATION_MODE=rfc7591_dcr` | RFC 7591 DCR **or** thin adapter returning fixed client |
| `POST /dcr` | `rhsso_custom_dcr` + separate Handler | Marketplace-style; **not** on MCP hot path |
| CIMD fetch target | Usually **on client vendor host**, not MCP | AS (RH SSO) or adapter validates client's metadata URL |

---

## On Red Hat SSO — already exists (verify in tenant)

Standard OIDC/OAuth discovery; **no need to duplicate on sidecar**.

| Document | Typical URL (realm with path) |
|----------|-------------------------------|
| OpenID Connect Discovery | `{issuer}/.well-known/openid-configuration` |
| OAuth AS Metadata (RFC 8414) | `{issuer}/.well-known/oauth-authorization-server` |

Example issuer: `https://sso.redhat.com/auth/realms/redhat-external`

From discovery, clients obtain:

| Endpoint | Path (Keycloak-style) |
|----------|------------------------|
| Authorization | `{issuer}/protocol/openid-connect/auth` |
| Token | `{issuer}/protocol/openid-connect/token` |
| JWKS | `{issuer}/protocol/openid-connect/certs` |
| Introspection (sidecar use) | `{issuer}/protocol/openid-connect/token/introspect` |
| `registration_endpoint` | Only if realm enables RFC 7591 DCR |

**Pre-pilot checklist:** `curl` discovery JSON; confirm `code_challenge_methods_supported` includes `S256`; note whether `registration_endpoint` and `client_id_metadata_document_supported` exist.

---

## Discovery flow (client view)

```
1. GET/POST MCP URL → 401 + WWW-Authenticate (resource_metadata=…)
2. GET PRM on MCP host → authorization_servers[]
3. GET AS metadata on SSO host → authorize, token, (register…)
4. Browser login at SSO → access_token
5. MCP requests with Bearer → sidecar introspect → proxy to insights-mcp
```

---

## What NOT to put on the MCP host

| Avoid | Reason |
|-------|--------|
| Full copy of SSO `openid-configuration` | Duplication; clients follow `authorization_servers` |
| `/protocol/openid-connect/auth` on MCP Route | SSO owns user login |
| Introspection on MCP URL | Sidecar calls SSO internally; not a public client API |

Exception: an **auth adapter** product that *proxies* metadata for IdPs missing MCP fields—that is out of scope unless RH SSO metadata is incomplete.

---

## Other topics to research before development

| Topic | Why | Owner / action |
|-------|-----|----------------|
| **Pilot Route URL & path** | Drives `MCP_PUBLIC_URL`, PRM path, `resource`, audience | Platform: hostname, path (`/` vs `/mcp`) |
| **insights-mcp transport** | Streamable HTTP vs SSE; listen port; health path | Read prod Deployment / image docs |
| **Scope & audience** | `api.console`, `api.ocm`, resource indicator for MCP URL | SSO admin + google-lightspeed defaults |
| **Pre-registered clients** | Per [mcp-client-oauth-registration.md](mcp-client-oauth-registration.md): GE/Copilot need admin-created clients + redirect URIs | SSO: create clients; document IDs in Secret |
| **Redirect URIs** | Claude hosted: `https://claude.ai/api/mcp/auth_callback`; GE: `https://vertexaisearch.cloud.google.com/oauth-redirect`; VS Code/Copilot: product-specific | Match each pilot client |
| **Token validation strategy** | Introspection (lightspeed pattern) vs JWKS + `aud` | Prefer introspection for multi-client-id |
| **OpenShift Route** | TLS edge, path rewrite, whether `/.well-known/*` reaches sidecar | Cluster networking |
| **Egress & firewall** | Pod → `sso.redhat.com`, `console.redhat.com` | NetPol / corporate proxy |
| **Secrets** | Introspection client, optional GMA, no `insights-mcp-credentials` | ESO / namespace Secret pattern |
| **MCP vs A2A** | google-lightspeed is A2A; we are MCP PRM—see [mcp-protocol-authorization.md](mcp-protocol-authorization.md) | Design review |
| **Rate limiting / size limits** | Optional; lightspeed uses Redis for A2A | Defer unless required |

---

## Implementation priority (metadata)

1. `401` + `WWW-Authenticate` + `resource_metadata` on all protected MCP methods.
2. `GET /.well-known/oauth-protected-resource` (+ path suffix if MCP under subpath).
3. PRM `authorization_servers` → verified SSO discovery URL.
4. Introspection in sidecar (no public introspection endpoint).
5. Registration endpoints only if pilot clients need DCR/CIMD adapter (see [mcp-client-oauth-registration.md](mcp-client-oauth-registration.md)).

---

## References

- [MCP authorization tutorial](https://modelcontextprotocol.io/docs/tutorials/security/authorization)
- [RFC 9728 — Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728)
- [Claude — cross-host AS, 401 shape](https://claude.com/docs/connectors/building/authentication)
