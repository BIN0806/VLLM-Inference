.PHONY: help setup lint test-unit preflight preflight-remote preflight-k8s ssh-scan-host tunnel \
	phase1-build phase1-up test-phase1 benchmark-phase1 phase1-down diagnostics \
	k8s-render k8s-render-replicas phase3-acceptance phase4-acceptance sync-remote compose-env-check health

PROFILE ?= authoring
PHASE1_PROFILE ?= vast-single-gpu
K8S_PROFILE ?= vast-k3s-replica
PHASE4_PROFILE ?= vast-k3s-replicas
OVERLAY ?= vast-k3s
PYTHON ?= python3.12
COMPOSE_ENV_FILE ?= .env.local
COMPOSE_EXPORT ?= artifacts/compose.env
COMPOSE = docker compose --project-directory $(CURDIR) -f docker/compose.yaml --env-file $(COMPOSE_EXPORT)

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

preflight-k8s: ## Evaluate Kubernetes host facts (offline JSON or local Linux). Does not install.
	uv run python -m inference_platform.preflight.k8s_host_cli --profile $(K8S_PROFILE)

phase3-acceptance: ## Offline Phase 3 tests; set RUN_PHASE3=1 for live tunneled SSE
	./scripts/phase3_acceptance.sh

phase4-acceptance: ## Offline Phase 4A tests; set RUN_PHASE4=1 for live tunneled SSE/PromQL
	./scripts/phase4_acceptance.sh

ssh-scan-host: ## Capture a candidate host key, print SHA256, install only after verification
	./scripts/ssh_scan_host.sh

tunnel: ## SSH tunnel to remote vLLM (does not mutate the GPU host)
	./scripts/open_vllm_tunnel.sh

compose-env-check: ## Require COMPOSE_ENV_FILE and prove profile/Compose agreement
	@test -f "$(COMPOSE_ENV_FILE)" || { \
		echo "error: $(COMPOSE_ENV_FILE) is missing."; \
		echo "Copy .env.example to .env.local. Compose interpolation does not read service env_file:."; \
		exit 1; \
	}
	mkdir -p artifacts
	uv run python -m inference_platform.compose export --profile $(PROFILE) --env-file $(COMPOSE_ENV_FILE) --out $(COMPOSE_EXPORT)

phase1-build: ## Build the pinned vLLM wrapper image (Linux NVIDIA host)
	$(MAKE) compose-env-check PROFILE=$(PHASE1_PROFILE)
	$(COMPOSE) build

phase1-up: ## Start compose vLLM (Linux NVIDIA host only)
	$(MAKE) compose-env-check PROFILE=$(PHASE1_PROFILE)
	$(COMPOSE) up -d

test-phase1: ## Live Phase 1 tests (requires RUN_PHASE1=1 and a ready endpoint)
	RUN_PHASE1=1 uv run pytest tests/integration/test_phase1.py -m gpu

benchmark-phase1: ## Contract-driven Phase 1 benchmark
	uv run python benchmarks/phase1_load.py --profile $(PHASE1_PROFILE)

phase1-down: ## Stop compose vLLM
	$(MAKE) compose-env-check PROFILE=$(PHASE1_PROFILE)
	$(COMPOSE) down

diagnostics: ## Write a redacted local diagnostics file under artifacts/
	uv run python scripts/collect_diagnostics.py

health: ## Probe VLLM_BASE_URL /health (tunneled or local)
	./scripts/check_vllm_health.sh

k8s-render: ## Render Phase 3 Kubernetes YAML from K8S_PROFILE (does not apply)
	uv run python -m inference_platform.k8s.render --profile $(K8S_PROFILE) --out infra/kubernetes/base
	@echo "Overlay=$(OVERLAY). Do not kubectl apply until a GPU VM is approved."

k8s-render-replicas: ## Render Phase 4A StatefulSet overlay (does not apply)
	uv run python -m inference_platform.k8s.render --profile $(PHASE4_PROFILE) --out infra/kubernetes/overlays/vast-k3s-replicas
	@echo "Do not kubectl apply until a two-GPU VM and k3s cluster exist. Do not install KEDA."

sync-remote: ## Copy the repo to the GPU host without secrets (requires INFERENCE_ALLOW_REMOTE=1)
	./scripts/sync_to_remote.sh
