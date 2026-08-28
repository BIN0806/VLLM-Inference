# Operations (Phase 0 skeleton)

Full operational runbooks belong to later phases. Phase 0 provides:

- Authoring setup: `make setup`, `make lint`, `make test-unit`, `make preflight`
- Vast Phase 1 client path: `docs/runbooks/vast-phase1.md`
- Diagnostics: `make diagnostics` (local, redacted)
- Remote sync (after startup): `make sync-remote` with `INFERENCE_ALLOW_REMOTE=1`

Do not stop, restart, or kill a loading vLLM process. Kubernetes, Ray, Prometheus, and KEDA are not operated in Phase 0.
