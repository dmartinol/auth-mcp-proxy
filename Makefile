.PHONY: install lint format typecheck test check build push run run-auth

IMAGE ?= quay.io/dmartino/auth-mcp-proxy
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

PYTHON ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)
PIP ?= $(PYTHON) -m pip

# Local dev defaults (override on CLI, e.g. make run SKIP_JWT_VALIDATION=false)
MCP_UPSTREAM_URL ?= http://127.0.0.1:9000
MCP_PUBLIC_URL ?= http://localhost:8080/mcp
SKIP_JWT_VALIDATION ?= true

install:
	@test -x .venv/bin/python || $(PYTHON) -m venv .venv
	$(PIP) install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check auth_mcp_proxy tests
	$(PYTHON) -m ruff format --check auth_mcp_proxy tests

format:
	$(PYTHON) -m ruff format auth_mcp_proxy tests
	$(PYTHON) -m ruff check --fix auth_mcp_proxy tests

typecheck:
	$(PYTHON) -m mypy auth_mcp_proxy

test:
	$(PYTHON) -m pytest -q

check: lint typecheck test

build:
	podman build -t $(IMAGE):$(TAG) -t $(IMAGE):latest -f Containerfile .

push: build
	podman push $(IMAGE):$(TAG)
	podman push $(IMAGE):latest

run:
	MCP_UPSTREAM_URL=$(MCP_UPSTREAM_URL) \
	MCP_PUBLIC_URL=$(MCP_PUBLIC_URL) \
	SKIP_JWT_VALIDATION=$(SKIP_JWT_VALIDATION) \
	$(PYTHON) -m auth_mcp_proxy.main

# SSO introspection enabled — requires RED_HAT_SSO_CLIENT_ID and RED_HAT_SSO_CLIENT_SECRET
run-auth:
	@test -n "$$RED_HAT_SSO_CLIENT_ID" || (echo "Set RED_HAT_SSO_CLIENT_ID (and SECRET) in .env or env"; exit 1)
	MCP_UPSTREAM_URL=$(MCP_UPSTREAM_URL) \
	MCP_PUBLIC_URL=$(MCP_PUBLIC_URL) \
	$(PYTHON) -m auth_mcp_proxy.main