# Kubernetes deploy — SSO pilot

Parallel stack for SSO-protected Insights MCP. Production namespace `tfigenbl-insights-mcp` is **not** modified.

## Prerequisites

- Image `quay.io/dmartino/auth-mcp-proxy` pushed (see repo `Makefile`)
- Prod `insights-mcp` image reference for the second container
- Red Hat SSO introspection client (`RED_HAT_SSO_CLIENT_ID` / `SECRET`)
- Pilot Route hostname; update `MCP_PUBLIC_URL` and Route host/path to match

## Apply order

Pilot namespace: **`dmartino-insights-mcp-sso`**. Create it before any other pilot resources.

1. Edit placeholders in `deploy/k8s/pilot/`:
   - `configmap-auth-mcp-proxy.yaml` — `MCP_PUBLIC_URL`, issuer, scopes
   - `deployment-auth-insights-mcp.yaml` — `insights-mcp` image
   - `route-auth-insights-mcp.yaml` — host and path

2. Create the namespace:

   ```bash
   oc apply -f deploy/k8s/pilot/namespace.yaml
   ```

3. Create Secret from example (do not commit real credentials):

   ```bash
   cp deploy/k8s/pilot/secret-auth-mcp-proxy.yaml.example \
      deploy/k8s/pilot/secret-auth-mcp-proxy.yaml
   # edit values, then:
   oc apply -f deploy/k8s/pilot/secret-auth-mcp-proxy.yaml
   ```

4. Apply the remaining manifests:

   ```bash
   oc apply -f deploy/k8s/pilot/configmap-auth-mcp-proxy.yaml
   oc apply -f deploy/k8s/pilot/deployment-auth-insights-mcp.yaml
   oc apply -f deploy/k8s/pilot/service-auth-insights-mcp.yaml
   oc apply -f deploy/k8s/pilot/route-auth-insights-mcp.yaml
   ```

5. Verify prod Route in `tfigenbl-insights-mcp` still works.

## Wiring checklist

| Check | |
|-------|---|
| `MCP_PUBLIC_URL` = `https://<route-host><route-path>` | |
| Service targets sidecar port `http` (8080), not `insights-mcp` alone | |
| No `insights-mcp-credentials` in pilot Deployment | |
| MCP clients use OAuth against Red Hat SSO (pre-registered for v1) | |

## Testing

Follow [docs/testing.md](../docs/testing.md) — Cursor HTTP MCP + OAuth is the primary pilot path.
