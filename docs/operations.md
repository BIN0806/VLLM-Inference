# Operations

- Architecture decisions: [decisions/README.md](decisions/README.md)
- Authoring setup: `make setup`, `make lint`, `make test-unit`, `make preflight`
- Vast Phase 1 client path: `docs/runbooks/vast-phase1.md`
- Phase 3 (accepted 1.5B AWQ on k3s): [k3s-replica-1.5b-status.md](runbooks/k3s-replica-1.5b-status.md), [vast-k3s-rental.md](runbooks/vast-k3s-rental.md), [k3s-nvidia.md](runbooks/k3s-nvidia.md), [k3s-acceptance.md](runbooks/k3s-acceptance.md)
- Phase 4A (accepted one 1.5B replica + Prometheus scrape): [k3s-replicas-prometheus-status.md](runbooks/k3s-replicas-prometheus-status.md), [k3s-replicas-prometheus.md](runbooks/k3s-replicas-prometheus.md)
- Diagnostics: `make diagnostics` (local, redacted)
- Remote sync (after startup): `make sync-remote` with `INFERENCE_ALLOW_REMOTE=1`

Do not stop, restart, or kill a loading vLLM process. Phase 4A accepted
Prometheus scrape of one warm replica. Do not install KEDA, expose public
ports, scale to two replicas, or attempt scale-to-zero until those gates
are approved.
