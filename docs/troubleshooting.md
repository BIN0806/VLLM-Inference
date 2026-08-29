# Troubleshooting

## CUDA or NVIDIA runtime not visible

Expected on the macOS authoring workstation. GPU gates run over SSH on Linux NVIDIA hosts. `nvidia-smi` missing locally is SKIP for `authoring`, not PASS.

## SSH host key verification failed

Do not set `StrictHostKeyChecking=no`. Capture a candidate key with `make ssh-scan-host`, compare the printed SHA256 fingerprint out of band, then rerun with `EXPECTED_FINGERPRINT=SHA256:...` or `CONFIRM=yes`. Keys are stored in `.ssh/known_hosts` in this repository. A mismatched existing key is a hard error.

## Compose interpolation ignored `.env.local`

`env_file:` does not feed `${VAR}` substitution. Use `make compose-env-check` (or `phase1-up`), which requires `COMPOSE_ENV_FILE` (default `.env.local`) and fails if the profile model/revision/context/TP disagrees with that file.

## Health never becomes ready

Ready is HTTP 200 only. 401 usually means an API key is required or wrong. 404 means the health path is wrong. Timeouts include the last status or exception.

## Model download / Xet failures

On some Vast hosts the Xet route fails. Set `HF_HUB_DISABLE_XET=1`.

## OOM during startup or load

Record GPU VRAM, model weights, `max_model_len`, `max_num_seqs`, and `gpu_memory_utilization`. Do not silently switch models. Explicit `ALLOW_MODEL_FALLBACK=true` is required and cannot pass the original gate.

## Shared-memory exhaustion

Compose uses `shm_size: 8gb` and `ipc: host`. Raise `shm_size` on Linux GPU hosts if NCCL/multiprocessing fails.

## Insufficient GPUs for TP

Preflight refuses `tensor_parallel_size` greater than visible GPUs. `ALLOW_TP_FALLBACK` is explicit and cannot pass the original TP gate.

## Kubernetes / KEDA / metrics / Ray

Phase 3 accepted one k3s 1.5B AWQ replica. Prometheus, KEDA, Ray, and
scale-to-zero were not installed. See
`docs/runbooks/k3s-replica-1.5b-status.md`. Multi-node Ray is
`NOT RUN — HARDWARE UNAVAILABLE`.

## vLLM crash-loop: `VLLM_PORT appears to be a URI`

Kubernetes service links inject `VLLM_PORT=tcp://…` from a Service named
`vllm`. Set `enableServiceLinks: false` on the pod spec. Do not publish the
Service to work around it.

## Streams dropped during shutdown / cold-start from zero

Phase 4C holds one request at the HTTP interceptor while the StatefulSet
scales 0→1. Client timeout must exceed the 420 s request budget. A 502/504
or a retried client is a failed cold-start, not a success. See
`docs/runbooks/k3s-replicas-http.md`.
