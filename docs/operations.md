# Operations

The live lab is closed and no rental is expected to be running. These pages are
reproducibility and evidence records, not authorization to provision a new VM.

## Current state

- Final accepted tag:
  `phase4-vast-k3s-2xa4000-keda-http-pass`.
- Phase 4 PR merged to `main`.
- Final local suite and merge CI passed.
- SSH forwards, k3s, Compose, GPU workers, and host listeners were stopped.
- The final Vast VM was deleted; VM-local PVCs and caches are gone.
- No public inference endpoint exists.

See [Final project status](project-status.md) and
[rental closeout](runbooks/vast-rental-closeout.md).

## Offline authoring workflow

```bash
cp .env.example .env.local
uv sync --python 3.12 --extra dev
make lint
make test-unit
make preflight PROFILE=authoring
```

The expected authoring preflight result is WARN when Docker, disk, or NVIDIA
hardware is unavailable. NVIDIA/Kubernetes/Ray live gates are SKIP, never PASS,
on the Mac.

Run `make help` for the complete command list. Live tests require explicit
`RUN_PHASE*=1`/remote approval flags so ordinary unit tests cannot contact a
rental accidentally.

## Safe validation order

For a newly approved GPU host:

1. Verify the provider offer, VM product type, disk, RAM, GPU count/VRAM,
   reliability, and expected duration.
2. Capture SSH host keys, compare fingerprints out of band, and enroll them in
   the project-local ignored `.ssh/known_hosts`.
3. Run read-only discovery before installing, stopping, or replacing anything.
4. Select a profile only after hardware fit is known. Do not silently change
   models or TP.
5. Run offline render/tests before remote apply.
6. Keep application access on remote loopback and use SSH forwarding.
7. Execute one gate at a time and preserve sanitized evidence.
8. Teardown in reverse dependency order and confirm provider deletion.

## Runbook index

### Foundation and single-GPU

- [Vast Phase 1 client path](runbooks/vast-phase1.md)
- [Compose validation status](runbooks/compose-1.5b-status.md)

### Kubernetes and NVIDIA

- [Vast VM rental checklist](runbooks/vast-k3s-rental.md)
- [k3s and NVIDIA checklist](runbooks/k3s-nvidia.md)
- [Phase 3 acceptance client path](runbooks/k3s-acceptance.md)
- [Phase 3 accepted status](runbooks/k3s-replica-1.5b-status.md)

### Observability and autoscaling

- [Phase 4A Prometheus procedure](runbooks/k3s-replicas-prometheus.md)
- [Phase 4A accepted status](runbooks/k3s-replicas-prometheus-status.md)
- [Phase 4B KEDA procedure](runbooks/k3s-replicas-keda.md)
- [Phase 4B accepted status](runbooks/k3s-replicas-keda-status.md)
- [Phase 4C HTTP scale-to-zero procedure](runbooks/k3s-replicas-http.md)
- [Phase 4C accepted status](runbooks/k3s-replicas-http-status.md)

### Closeout

- [Vast rental closeout](runbooks/vast-rental-closeout.md)

Procedure pages preserve phase-specific STOP boundaries. Status pages preserve
what was and was not installed at that moment. Later phases may have completed
an earlier “not tested” item; use [Final project status](project-status.md) for
the final matrix.

## Operational invariants

- Do not stop or replace a loading vLLM process without explicit approval.
- Do not disable SSH host-key checking.
- Do not send credentials over non-loopback plaintext HTTP.
- Do not expose raw vLLM, Prometheus, or the interceptor publicly.
- Do not run two HPAs/ScaledObjects against the same StatefulSet.
- Do not scale a TP/PP/Ray rank independently.
- Do not treat a patch fragment as a standalone Kubernetes manifest.
- Do not describe `local-path` as provider-persistent storage.
- Do not compare benchmark numbers across different GPUs as a topology result.
- Do not claim a fallback as passing the original gate.

## Teardown order

1. Stop load generators and wait for active requests to drain.
2. Close exact `kubectl port-forward` and SSH-forward PIDs with SIGTERM.
3. Capture the final sanitized object, metrics, disk, RAM, and GPU state.
4. Scale or stop the serving workload gracefully.
5. Stop k3s with systemd; avoid broad process matching and SIGKILL.
6. If Compose is running, use the same project/env inputs with
   `docker compose down`.
7. Confirm application listeners are gone and GPUs have no compute processes.
8. Delete the provider instance through the approved operator path.
9. Confirm the provider response and later connection failure/UI state.
10. Record that node-local volumes and caches were deleted with the VM.

## Evidence rules

Tracked reports may include hardware class, component versions, aggregate
metrics, sanitized failures, and claim boundaries. Keep live addresses, SSH
ports, instance IDs, fingerprints, tokens, kubeconfigs, raw logs, and artifacts
out of Git.

Diagnostics write redacted local artifacts. The authoring Git repository—not an
ephemeral rental—is the source of truth.
