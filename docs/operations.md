# Operations

- Architecture decisions: [decisions/README.md](decisions/README.md)
- Authoring setup: `make setup`, `make lint`, `make test-unit`, `make preflight`
- Vast Phase 1 client path: `docs/runbooks/vast-phase1.md`
- Phase 3 (accepted 1.5B AWQ on k3s): [k3s-replica-1.5b-status.md](runbooks/k3s-replica-1.5b-status.md), [vast-k3s-rental.md](runbooks/vast-k3s-rental.md), [k3s-nvidia.md](runbooks/k3s-nvidia.md), [k3s-acceptance.md](runbooks/k3s-acceptance.md)
- Phase 4A (accepted one 1.5B replica + Prometheus scrape): [k3s-replicas-prometheus-status.md](runbooks/k3s-replicas-prometheus-status.md), [k3s-replicas-prometheus.md](runbooks/k3s-replicas-prometheus.md)
- Phase 4B (accepted KEDA 1→2→1): [k3s-replicas-keda-status.md](runbooks/k3s-replicas-keda-status.md), [k3s-replicas-keda.md](runbooks/k3s-replicas-keda.md)
- Phase 4C (accepted HTTP interceptor lab 0→1): [k3s-replicas-http-status.md](runbooks/k3s-replicas-http-status.md), [k3s-replicas-http.md](runbooks/k3s-replicas-http.md)
- Compose closeout (accepted 1.5B AWQ on GPU 0): [compose-1.5b-status.md](runbooks/compose-1.5b-status.md)
- Rental teardown: [vast-rental-closeout.md](runbooks/vast-rental-closeout.md)
- Diagnostics: `make diagnostics` (local, redacted)
- Remote sync (after startup): `make sync-remote` with `INFERENCE_ALLOW_REMOTE=1`

Do not stop, restart, or kill a loading vLLM process. Phase 4C is accepted
as a **single-node lab** with **one** interceptor replica. Phase 4B proved
Prometheus-driven **1→2**; Phase 4C proved interceptor-driven **0→1**. HTTP
**0→2** was not tested. Do not expose public ports, deploy 9B, or claim
production TLS/HA.

Compose 1.5B on GPU 0 is accepted
([compose-1.5b-status.md](runbooks/compose-1.5b-status.md)). Rental destroy
is an operator action recorded in
[vast-rental-closeout.md](runbooks/vast-rental-closeout.md).
