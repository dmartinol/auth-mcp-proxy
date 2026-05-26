# MCP client OAuth & client registration (research)

Concise survey for framework design. Sources linked; behavior varies by product version.

**MCP spec (2025-11-25):** clients SHOULD try **pre-registration → CIMD → RFC 7591 DCR → manual** based on AS metadata ([authorization spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)).

**Red Hat SSO custom `/dcr`:** GMA-backed, registration-time only — see [google-lightspeed-agent-oauth.md](google-lightspeed-agent-oauth.md) (Marketplace Handler). **Not** OIDC `registration_endpoint`.

---

## What is CIMD?

**CIMD** = **Client ID Metadata Document** (IETF [draft](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-client-id-metadata-document-00); MCP [SEP-991](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#client-id-metadata-documents)).

### Idea

Instead of calling a registration API to *create* a client record (DCR), the MCP **client uses an HTTPS URL as its `client_id`**. That URL returns a small JSON document describing the app (name, logo, redirect URIs, etc.). The **authorization server fetches and validates** that document when the user connects.

Think of it as a **driver’s license hosted on the client vendor’s domain**: the IdP checks the license URL once (with caching), not a central “registration desk” that mints a new client row per install.

### Flow (simplified)

```
1. MCP client starts OAuth with client_id = https://vendor.example/oauth/client-metadata.json
2. Authorization server GETs that URL
3. AS checks: HTTPS, valid JSON, client_id field in JSON == URL exactly, redirect_uris OK
4. AS shows consent screen using client_name / logo_uri from the document
5. Standard authorization_code + PKCE → access token
```

No `POST /register` step on the IdP for each new connection.

### CIMD vs DCR vs pre-registration

| Mechanism | Who creates the OAuth client? | `client_id` shape | IdP database growth |
|-----------|--------------------------------|-------------------|------------------------|
| **Pre-registration** | Admin, ahead of time | Opaque string (`abc-123`) | One row per app you configure |
| **DCR (RFC 7591)** | Client calls `registration_endpoint` at connect time | Opaque string, new per registration | **Many rows** (Claude warns: new client per fresh connection) |
| **CIMD** | Client vendor publishes metadata at a stable URL | **The metadata URL itself** | AS may cache metadata; no per-user client row |

MCP spec priority (2025-11-25): try **pre-registration** if the client already has creds → **CIMD** if AS advertises support → **DCR** as fallback → prompt user for manual client info.

### What the authorization server must advertise

For MCP clients to choose CIMD, OAuth Authorization Server Metadata should include:

- `"client_id_metadata_document_supported": true`
- `"token_endpoint_auth_methods_supported"` including `"none"` when the client is a **public** client at the token endpoint (Claude’s CIMD path uses this)

If CIMD is not advertised, spec-compliant clients fall back to DCR or pre-registration.

### Example metadata document

Hosted at `https://claude.ai/oauth/claude-code-client-metadata` (illustrative shape):

```json
{
  "client_id": "https://claude.ai/oauth/claude-code-client-metadata",
  "client_name": "Claude Code",
  "redirect_uris": ["http://127.0.0.1/callback", "http://localhost/callback"]
}
```

The `client_id` property **must** match the document URL character-for-character.

### Why MCP moved toward CIMD

- **DCR at scale**: agents reconnect often; each DCR call can create another OAuth client in Keycloak/Red Hat SSO → operational noise and consent-screen clutter.
- **Trust model**: identity is tied to a **domain the vendor controls** (the metadata URL), not an anonymous registration POST.
- **Stateless for operators**: no registration endpoint to harden against flooding; optional HTTP caching of metadata.

Trade-off: the AS (or a framework adapter) must **fetch and validate** remote JSON safely (HTTPS, SSRF controls, cache TTL).

### CIMD and this project (Red Hat SSO)

- Red Hat SSO / Keycloak do **not** natively speak CIMD end-to-end today the way greenfield MCP tutorials assume; adapters may **accept a CIMD-style `client_id` URL** and map it to a **pre-provisioned** upstream `client_id` ([mcp-auth-adapter pattern](https://dev.to/velias/bridge-the-gap-between-your-idp-and-the-mcp-world-3gbn)).
- **RH custom `/dcr`** (GMA) is a third path—**once at Gemini/marketplace registration**, via Marketplace Handler; see [google-lightspeed-agent-oauth.md](google-lightspeed-agent-oauth.md).
- For **ChatGPT** and **hosted Claude**, CIMD is increasingly the **preferred** path; for **Copilot Enterprise** and **Gemini Enterprise**, plan on **pre-registration** regardless of CIMD.

Framework setting: `CLIENT_REGISTRATION_MODE=cimd` means advertise CIMD in AS metadata and implement fetch/validate (or bridge to fixed RH SSO clients)—not the same as enabling `rhsso_custom_dcr`.

---

## Summary matrix

| Client | OAuth for remote MCP | RFC 7591 DCR (`registration_endpoint`) | CIMD | Pre-registered client | Notes for RH SSO `/dcr` |
|--------|----------------------|----------------------------------------|------|----------------------|-------------------------|
| **ChatGPT** (Apps / connectors) | Required for custom remote MCP | Supported when configured; prefers **CIMD** | **Yes** (preferred) | Via connector / app setup | Register Gemini/ChatGPT app in IdP; expose standard PRM + AS metadata; add **adapter** if only RH `/dcr` exists |
| **Copilot Enterprise** (VS Code / IDE) | Yes (HTTP MCP); PAT alternative | **Unlikely** for custom servers | Unknown | **Primary** for enterprise/custom MCP | Admin supplies OAuth client in connector config; Entra manual registration for MS Graph MCP ([Learn](https://learn.microsoft.com/en-us/graph/mcp-server/use-enterprise-mcp-server-copilot-studio)) |
| **Gemini Enterprise** (custom MCP datastore) | Required | **No** — admin registers GE as OAuth client in IdP | N/A | **Required** | Fixed redirect `https://vertexaisearch.cloud.google.com/oauth-redirect`; paste Client ID/Secret in GE UI ([docs](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server)) |
| **Claude Desktop** | Via `mcp-remote` bridge for remote HTTP | **Yes** if server advertises `registration_endpoint` | **Yes** (hosted Claude); Desktop uses own CIMD for Claude Code | **`--static-oauth-client-info`** skips DCR | Native remote OAuth immature; pre-register + `mcp-remote` common ([mcp-remote](https://github.com/geelen/mcp-remote)) |

---

## Per-target detail

### ChatGPT

- Custom remote MCP: OAuth required; static API keys not supported for connectors ([OpenAI MCP docs](https://developers.openai.com/api/docs/mcp)).
- Registration: recommends **CIMD** when AS supports it; **DCR remains supported** when configured ([Authentication for apps](https://developers.openai.com/api/docs/mcp)).
- Implication: framework should advertise AS metadata (`client_id_metadata_document_supported`, `registration_endpoint`) per pilot audience; RH custom `/dcr` needs a **compatibility shim** (e.g. synthetic `registration_endpoint` or documented pre-registration).

### GitHub Copilot Enterprise

- Remote HTTP MCP in VS Code: OAuth **or** PAT in `mcp.json` ([enterprise MCP config](https://github.com/github/docs/blob/main/content/copilot/how-tos/provide-context/use-mcp/enterprise-configuration.md)).
- No documented self-service DCR for **arbitrary** third-party MCP servers; GitHub’s own MCP uses platform OAuth.
- Implication: **pre-register** OAuth client(s) per org; configure redirect URIs for VS Code / Copilot; framework `CLIENT_REGISTRATION_MODE=pre_registered`.

### Gemini Enterprise

- Custom MCP connector: operator registers **Gemini Enterprise** as a confidential OAuth client in IdP; enters Client ID, Secret, Auth URL, Token URL, scopes in admin UI ([set up custom MCP server](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server)).
- **No** dynamic registration in Enterprise UI.
- Implication: one stable `client_id`/`client_secret` per GE deployment; RH `/dcr` not used by GE—use GMA/manual client creation once, store creds in GE config.

### Claude Desktop

- Hosted connectors (claude.ai): `oauth_dcr`, `oauth_cimd`, `oauth_anthropic_creds` ([Claude connector auth](https://claude.com/docs/connectors/building/authentication)).
- **Claude Desktop** remote HTTP: typically **stdio + `mcp-remote`**; DCR automatic if `registration_endpoint` present; else `--static-oauth-client-info` ([pro_tips guide](https://github.com/pieces-app/pro_tips/blob/main/guides/MCP/Bridging%20Local%20MCP%20Clients%20to%20Remote%20Servers%20with%20mcp-remote.md)).
- DCR on every reconnect can flood IdP—Anthropic recommends CIMD or pre-registered creds for high traffic.
- Implication: pilot should support **pre_registered** + optional **rfc7591_dcr**; document `mcp-remote` JSON for Desktop users.

---

## Framework implications

1. **`CLIENT_REGISTRATION_MODE`** must be pluggable (not DCR-only).
2. **Advertise metadata** matching the mode (e.g. omit `registration_endpoint` when mode is `pre_registered` only).
3. **RH SSO custom `/dcr`**: `rhsso_custom_dcr` — separate service at **registration time** ([google-lightspeed-agent-oauth.md](google-lightspeed-agent-oauth.md)); not for ChatGPT/Copilot/GE/Claude unless wrapped.
4. **Default for Enterprise pilots:** `pre_registered` + introspection; enable `rfc7591_dcr` or `cimd` only when a target client requires it.
5. **Per-client allowlist** (optional): map `client_id` → registration profile for multi-tenant pilots.

---

## References

- [MCP Authorization (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [Claude connector authentication](https://claude.com/docs/connectors/building/authentication)
- [OpenAI — Building MCP servers / auth](https://developers.openai.com/api/docs/mcp)
- [Gemini Enterprise — custom MCP OAuth](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server)
- [GitHub Copilot — enterprise MCP](https://github.com/github/docs/blob/main/content/copilot/how-tos/provide-context/use-mcp/enterprise-configuration.md)
- [mcp-remote](https://github.com/geelen/mcp-remote)
