# Operations

- Authoring setup: `make setup`, `make lint`, `make test-unit`, `make preflight`
- Vast Phase 1 client path: `docs/runbooks/vast-phase1.md`
- Phase 3 (accepted 1.5B AWQ on k3s): [k3s-replica-1.5b-status.md](runbooks/k3s-replica-1.5b-status.md), [vast-k3s-rental.md](runbooks/vast-k3s-rental.md), [k3s-nvidia.md](runbooks/k3s-nvidia.md), [k3s-acceptance.md](runbooks/k3s-acceptance.md)
- Diagnostics: `make diagnostics` (local, redacted)
- Remote sync (after startup): `make sync-remote` with `INFERENCE_ALLOW_REMOTE=1`

Do not stop, restart, or kill a loading vLLM process. Do not install or operate
Ray, Prometheus, or KEDA until a later approved gate. Phase 3 did not test
those. Scale-to-zero stays a separate later gate.

The next planned gate (not provisioned from this tree) is two schedulable
NVIDIA GPUs, Prometheus scraping first, then KEDA scaling one warm 1.5B AWQ
replica to two. Do not rent or install that from here.
