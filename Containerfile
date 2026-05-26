FROM python:3.12-slim-bookworm

WORKDIR /app

RUN useradd --create-home --uid 1001 appuser

COPY pyproject.toml README.md ./
COPY auth_mcp_proxy ./auth_mcp_proxy

RUN pip install --no-cache-dir . \
    && chown -R appuser:appuser /app

USER appuser

ENV LISTEN_HOST=0.0.0.0 \
    LISTEN_PORT=8080 \
    MCP_UPSTREAM_URL=http://127.0.0.1:8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

CMD ["auth-mcp-proxy"]
