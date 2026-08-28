# Troubleshooting

## CUDA or NVIDIA runtime not visible

Expected on the macOS authoring workstation. GPU gates run over SSH on Linux NVIDIA hosts. `nvidia-smi` missing locally is SKIP for `authoring`, not PASS.

## SSH host key verification failed

Do not set `StrictHostKeyChecking=no`. Run `make ssh-scan-host` once, then retry.

## Model download / Xet failures

On some Vast hosts the Xet route fails. Set `HF_HUB_DISABLE_XET=1`.

## OOM during startup or load

Record GPU VRAM, model weights, `max_model_len`, `max_num_seqs`, and `gpu_memory_utilization`. Do not silently switch models. Explicit `ALLOW_MODEL_FALLBACK=true` is required and cannot pass the original gate.

## Shared-memory exhaustion

Compose uses `shm_size: 8gb` and `ipc: host`. Raise `shm_size` on Linux GPU hosts if NCCL/multiprocessing fails.

## Insufficient GPUs for TP

Preflight refuses `tensor_parallel_size` greater than visible GPUs. `ALLOW_TP_FALLBACK` is explicit and cannot pass the original TP gate.

## Kubernetes / KEDA / metrics / Ray

Not executed in Phase 0. See `infra/*/README.md`. Multi-node Ray is `NOT RUN — HARDWARE UNAVAILABLE`.

## Streams dropped during shutdown / cold-start from zero

Later phases. First Kubernetes MVP uses one warm replica. Scale-to-zero needs a durable HTTP interceptor.
