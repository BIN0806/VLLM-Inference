# Phase 2 read-only preflight

Recorded from the macOS authoring workstation. **No vLLM process was started,
stopped, or replaced.** No public HTTP Bearer call was made. Phase 2A server
startup is **not** claimed. Multi-node Ray is **not** claimed.

SSH used the project `.ssh/known_hosts` enrollment workflow with
`StrictHostKeyChecking=yes`. Host addresses, fingerprints, and instance
identifiers are not published. Raw JSON: gitignored `artifacts/phase2/preflight.json`.

## Gate decision: **NO-GO to start Phase 2A**

Hardware can support native same-host TP=2 with conservative flags, but
preflight must not proceed to download or a second server while the Vast
template `vllm serve` is already loading. Disk free space is also below the
20–22 GiB download threshold; the pinned 9B snapshot is already on disk.

Do not interrupt that loading process. After it becomes healthy, OOMs, or the
user approves stopping it, Phase 2A can start with the proposed mp flags over
an SSH tunnel.

## Checklist

| Criterion | Observed | Gate |
|---|---|---|
| Two GPUs visible | 2 × NVIDIA GeForce RTX 3060 | GO |
| ~12 GiB VRAM each | 12288 MiB total, 11665 MiB free, 245 MiB used | GO |
| ≥20–22 GiB disk free | 24.0 GiB allocated; **5.39 GiB free** on `/` and `/workspace` | NO-GO for a new download |
| Pinned model on disk | `Qwen/Qwen3.5-9B` revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`, four of four `safetensors` shards (~18.0 GiB) | GO (no download needed) |
| No conflicting vLLM | Supervisor `vllm.sh` running `vllm serve` on `127.0.0.1:18000`; `VLLM::EngineCore` plus two `VLLM::Worker` (~236 MiB each) | NO-GO to start another |
| Shared memory | `/dev/shm` 23.0 GiB total, ~0 used | GO |
| TP=2 fit (proposed flags) | 9.0 GiB weights/rank vs 12 GiB; topology `ok` with `disk-tight` warn | CONDITIONAL GO |
| PCIe / NUMA | GPU0↔GPU1 **SYS** (cross-NUMA SMP); GPUs on NUMA 0 and 1 | WARN (slower TP, not a hard fail) |

## Proposed Phase 2A (not started)

- Profile: `vast-two-gpu` (`compute: multi-gpu-tp`)
- Model: `Qwen/Qwen3.5-9B` @ `c202236235762e1c871ad0ccb60c8ee5ba337b9a`
- `tensor_parallel_size=2`, `pipeline_parallel_size=1`, `distributed_executor_backend=mp`
- `max_model_len=8192`, `max_num_seqs=2`, `gpu_memory_utilization=0.90`
- `HF_HUB_DISABLE_XET=1`
- `--enforce-eager` if 12 GiB headroom requires it
- API acceptance only through an SSH tunnel to loopback HTTP. Do not send
  credentials through public plaintext HTTP.

The template process currently uses `--max-model-len 32000` and
`--max-num-seqs 8`. That is **not** the Phase 2A contract and is likely too
large for 12 GiB GPUs. Preflight did not change it.

## Software (read-only `pip show` / `nvidia-smi`)

- Driver 580.126.09, reported CUDA 13.0
- Python 3.12.13
- vLLM 0.27.1, PyTorch 2.13.0+cu130, Ray 2.58.0 (installed; Phase 2A does not use Ray)
- CPU: 64 threads, Intel Xeon E5-2698B v3 @ 2.00 GHz
- RAM: 188.8 GiB total, 163.1 GiB available

## Processes and ports

Supervisor is running portal helpers including `vllm.sh`, `ray.sh`, and
`caddy.sh`. Ray GCS/dashboard are up on this **one** host. That is not
multi-node Ray.

vLLM is bound in the template to remote `127.0.0.1:18000`. Workers were still
in early load (hundreds of MiB, not a finished 9B replica) at collection time.

## Security backlog

Remote HTTPS clients should later refuse credentials when `VLLM_TLS_VERIFY=false`
unless a lab-only override is set. Phase 2A uses a loopback SSH tunnel, so this
does not block the gate.

## Next

1. Do not start a second vLLM.
2. Wait for the template load to finish or fail, or get approval to stop it.
3. Then start Phase 2A mp TP=2 with the flags above and tunnelled acceptance.
4. After Phase 2A passes, request approval for Phase 2B (same-host Ray only).
