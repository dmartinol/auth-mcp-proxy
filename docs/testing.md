# Pilot testing guide

How to verify the SSO-protected Insights MCP stack after deploy. Replace placeholders with your pilot values.

| Placeholder | Example | Your value |
|-------------|---------|------------|
| `PILOT_MCP_URL` | `https://insights-mcp-sso.example.com/mcp` | Must match `MCP_PUBLIC_URL` in the sidecar ConfigMap |
| `PILOT_PRM_URL` | `https://insights-mcp-sso.example.com/.well-known/oauth-protected-resource/mcp` | From `401` `resource_metadata` or path rules in [research/mcp-oauth-metadata-and-discovery.md](../research/mcp-oauth-metadata-and-discovery.md) |

Registration differences per client: [research/mcp-client-oauth-registration.md](../research/mcp-client-oauth-registration.md).

---

## Prerequisites

- Pilot Deployment healthy (`auth-mcp-proxy` + `insights-mcp`); Route points at the **sidecar** Service port.
- Red Hat SSO introspection client configured in the pilot Secret.
- For agent-based tests: OAuth client **pre-registered** in SSO with redirect URIs required by that product (see sections below).
- Production `insights-mcp` in `tfigenbl-insights-mcp` still reachable (regression).

---

## 1. HTTP smoke (curl)

No MCP client required. Confirms the sidecar acts as an OAuth resource server.

### 1.1 Unauthenticated MCP request → 401

```bash
curl -si -X POST "${PILOT_MCP_URL}" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}},"id":1}'
```

Expect:

- Status `401 Unauthorized`
- Header `WWW-Authenticate` containing `Bearer` and `resource_metadata="..."`

### 1.2 Protected Resource Metadata

Use the URL from `resource_metadata`, or derive from `PILOT_MCP_URL`:

```bash
curl -s "${PILOT_PRM_URL}" | jq .
```

Expect JSON including:

- `resource` — exactly `PILOT_MCP_URL`
- `authorization_servers` — Red Hat SSO issuer URL
- `scopes_supported` — includes scopes required for Insights (e.g. `api.console`, `api.ocm`)

### 1.3 Sidecar health (if exposed on Route or port-forward)

```bash
curl -s "https://<sidecar-host>/health"
curl -s "https://<sidecar-host>/ready"
```

---

## 2. Bearer token without MCP UI (ocm)

Validates introspection + proxy + Bearer pass-through using a user token from Red Hat SSO.

```bash
ocm login --use-auth-code
TOKEN=$(ocm token)
```

Repeat the initialize request with Bearer (MCP Streamable HTTP needs `Accept`; the sidecar adds it if omitted):

```bash
curl -si -X POST "${PILOT_MCP_URL}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}},"id":1}'
```

Expect: not `401` (may be `200` or MCP-level JSON-RPC response from upstream). If `403`, check token scopes and audience vs `PILOT_MCP_URL`.

Reference: [google-lightspeed-agent-oauth.md](../research/google-lightspeed-agent-oauth.md#local-testing).

---

## 3. Primary path: Cursor

Recommended for day-to-day pilot testing (native HTTP MCP + OAuth discovery).

1. Ensure an OAuth client exists in Red Hat SSO for Cursor with redirect URIs your environment allows (or use a client already used for Red Hat console access if policy allows).
2. In Cursor: add an MCP server — type **HTTP**, URL = `PILOT_MCP_URL`.
3. On connect, Cursor should hit `401`, read PRM, open browser for Red Hat SSO login.
4. After consent, tools should list; run a read-only Insights tool (e.g. list systems).
5. Confirm pilot pod has **no** `insights-mcp-credentials` Secret mounted and tool calls still succeed.

**Pass criteria:** OAuth in browser; tools work; sidecar logs show authenticated proxy (no token values in logs).

---

## 4. Claude Desktop (remote HTTP)

Claude Desktop often uses **stdio** locally; for remote HTTP MCP with OAuth, use **`mcp-remote`** unless your build supports remote OAuth directly.

1. Pre-register an OAuth client in SSO (or use DCR only if your pilot advertises `registration_endpoint`).
2. Configure `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "insights-pilot": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "PILOT_MCP_URL",
        "--static-oauth-client-info",
        "@/path/to/oauth-client.json"
      ]
    }
  }
}
```

`oauth-client.json` contains `client_id` and `client_secret` from SSO admin (pre-registration).

3. Restart Claude Desktop; complete browser login when prompted.
4. Verify tools appear and a sample tool call works.

Details: [mcp-client-oauth-registration.md](../research/mcp-client-oauth-registration.md), [mcp-remote](https://github.com/geelen/mcp-remote).

---

## 5. VS Code / GitHub Copilot Enterprise

1. Pre-register OAuth client; configure redirect URIs for Copilot/VS Code MCP.
2. Add server to workspace or user `mcp.json` (HTTP), URL = `PILOT_MCP_URL`.
3. Use OAuth flow when prompted, or PAT only if your org policy uses PAT for custom MCP (see enterprise docs — OAuth is preferred for this pilot).

Reference: [GitHub Copilot enterprise MCP configuration](https://github.com/github/docs/blob/main/content/copilot/how-tos/provide-context/use-mcp/enterprise-configuration.md).

---

## 6. Gemini Enterprise (custom MCP connector)

Not DCR at connect time — admin registers Gemini Enterprise as a client in SSO.

1. In SSO: create client; redirect URI `https://vertexaisearch.cloud.google.com/oauth-redirect`.
2. In Gemini Enterprise admin: custom MCP datastore — enter Client ID, Secret, Authorization URL, Token URL, scopes, **MCP Server URL** = `PILOT_MCP_URL`.
3. Run connector login test from GE UI.

Reference: [Gemini Enterprise custom MCP setup](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server).

---

## 7. ChatGPT (Apps / connectors)

Custom remote MCP expects OAuth; may prefer CIMD when SSO supports it. Pre-register or ensure AS metadata matches your pilot registration mode.

1. Register app/connector with `PILOT_MCP_URL`.
2. Complete OAuth in browser; verify tools load.

Reference: [OpenAI MCP server auth](https://developers.openai.com/api/docs/mcp).

---

## 8. Negative tests

| Case | How | Expect |
|------|-----|--------|
| Missing Bearer | curl without `Authorization` | `401` + PRM |
| Expired token | Reuse old `TOKEN` | `401` |
| Wrong audience | Token for another resource | `401` or `403` |
| Missing scope | Token without `api.console` / `api.ocm` | `403` / insufficient_scope |

---

## 9. Acceptance checklist

Maps to [AGENTS.md](../AGENTS.md#pilot-checklist):

- [ ] Prod route in `tfigenbl-insights-mcp` unchanged
- [ ] §1 curl: `401` + valid PRM
- [ ] §2 or §3: authenticated MCP works
- [ ] §8: at least one negative case behaves correctly
- [ ] Pod: no static Insights credentials; Bearer forwarded to upstream (check sidecar/upstream logs, redacted)

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `401` but no browser OAuth in client | PRM `authorization_servers`; SSO discovery reachable from client network |
| OAuth works, tools empty / API errors | Token scopes; `insights-mcp` image; upstream logs |
| `403` after login | `REQUIRED_SCOPES`; SSO client scopes; audience / `resource` = `PILOT_MCP_URL` |
| PRM 404 | Route path vs well-known path; [metadata research](../research/mcp-oauth-metadata-and-discovery.md) |
| Works with `ocm token` but not Cursor | Separate pre-registered client + redirect URI for Cursor |
