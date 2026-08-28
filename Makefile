.PHONY: help setup lint test-unit preflight preflight-remote ssh-scan-host tunnel \
	phase1-build phase1-up test-phase1 benchmark-phase1 phase1-down diagnostics \
	k8s-render sync-remote

PROFILE ?= authoring
OVERLAY ?= local
PYTHON ?= python3.12

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  %-22s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## Create the Python 3.12 virtualenv and install pinned dependencies
	uv sync --python 3.12 --extra dev

lint: ## Format check and lint
	uv run ruff format --check src tests scripts benchmarks
	uv run ruff check src tests scripts benchmarks

test-unit: ## Offline unit tests (no GPU, Docker daemon, or cluster)
	uv run pytest tests/unit -m unit

preflight: ## Local authoring preflight for PROFILE (default authoring)
	uv run python -m inference_platform.preflight --profile $(PROFILE)

preflight-remote: ## Read-only remote discovery (requires INFERENCE_ALLOW_REMOTE=1)
	./scripts/preflight_remote.sh

ssh-scan-host: ## Record the remote SSH host key without disabling checking
	./scripts/ssh_scan_host.sh

tunnel: ## SSH tunnel to remote vLLM (does not mutate the GPU host)
	./scripts/open_vllm_tunnel.sh

phase1-build: ## Build the pinned vLLM wrapper image (Linux NVIDIA host)
	docker compose -f docker/compose.yaml build

phase1-up: ## Start compose vLLM (Linux NVIDIA host only)
	docker compose -f docker/compose.yaml up -d

test-phase1: ## Live Phase 1 tests (requires RUN_PHASE1=1 and a ready endpoint)
	RUN_PHASE1=1 uv run pytest tests/integration/test_phase1.py -m gpu

benchmark-phase1: ## Contract-driven Phase 1 benchmark
	uv run python benchmarks/phase1_load.py --profile $(PROFILE)

phase1-down: ## Stop compose vLLM
	docker compose -f docker/compose.yaml down

diagnostics: ## Write a redacted local diagnostics file under artifacts/
	uv run python scripts/collect_diagnostics.py

health: ## Probe VLLM_BASE_URL /health (tunneled or local)
	./scripts/check_vllm_health.sh

k8s-render: ## Placeholder until Phase 3; prints the overlay contract
	@echo "Kubernetes overlays are documented under infra/kubernetes and are unvalidated."
	@echo "OVERLAY=$(OVERLAY)"

sync-remote: ## Copy the repo to the GPU host without secrets (requires INFERENCE_ALLOW_REMOTE=1)
	./scripts/sync_to_remote.sh
