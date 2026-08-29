# Personal use

The simplest personal use is one pinned 1.5B AWQ vLLM container on a rented
Linux NVIDIA GPU, published only on remote loopback and reached through SSH.
Your Mac remains the authoring workstation and client.

This workflow serves pretrained models. It does not train or fine-tune them.

## Good personal projects

- A private writing, brainstorming, or summarization endpoint.
- Document classification or structured extraction.
- A coding or documentation assistant driven by your own client.
- Batch processing of notes or text files.
- A local application backend that expects an OpenAI-compatible API.
- Retrieval-augmented generation where a separate application owns document
  indexing/retrieval and sends selected context to vLLM.
- Learning GPU memory, streaming, observability, and Kubernetes operations.

Keep sensitive source material inside the SSH-tunneled path. A remote rental
still stores data in another operator's environment, so do not send material
whose policy forbids that.

## Recommended personal pathway

1. Start offline on the Mac.
2. Rent one Linux NVIDIA GPU only when needed.
3. Run the 1.5B AWQ Compose profile.
4. Reach it through SSH-tunneled loopback.
5. Stop Compose and destroy the rental after the session.
6. Add k3s/Prometheus/KEDA only when the learning goal specifically requires
   orchestration or autoscaling.

For most individual use, Compose is easier and cheaper than Kubernetes.

## Hardware and rental shape

For the already-validated personal path, prefer:

- Linux x86_64 NVIDIA host;
- at least 16 GiB VRAM for comfortable reproduction of the accepted 1.5B
  configuration;
- 16 GiB host RAM minimum, 32 GiB preferred;
- at least 80 GiB disk, preferably 100 GiB;
- NVIDIA driver compatible with the pinned container;
- reliable SSH and enough bandwidth for the initial model/image download.

The project observed about 14.15 GiB GPU allocation with
`gpu_memory_utilization=0.90` on an RTX A4000. vLLM intentionally reserves a
large arena, so model file size is not the same as runtime VRAM.

Do not assume Apple Metal can pass this CUDA/vLLM path. A separate Mac-native
runtime may be useful for very small local models, but that is outside this
repository's accepted deployment.

## 1. Prepare the authoring workstation

```bash
git clone https://github.com/BIN0806/VLLM-Inference.git
cd VLLM-Inference
uv sync --python 3.12 --extra dev
make lint
make test-unit
make preflight PROFILE=authoring
```

Copy the environment template:

```bash
cp .env.example .env.local
```

Keep `.env.local`, host keys, tokens, and rental information out of Git.

## 2. Select the personal model contract

Use:

| Setting | Value |
|---|---|
| Profile | `vast-k3s-replica` |
| Model | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` |
| Revision | `3ecffa0ceb27851800f45519bab9c457a04405e1` |
| Served name | `qwen2.5-1.5b-instruct-awq` |
| TP / PP | 1 / 1 |
| Executor | `mp` |
| Context | 8192 |
| Max sequences | 8 |
| Host bind | `127.0.0.1` |

The profile/export guard checks that `.env.local` agrees with the selected
contract. Do not silently substitute the 9B model.

## 3. Verify and sync the GPU host

Register your SSH public key with the provider before starting the VM. After
renting:

1. fill the connection fields in `.env.local`;
2. compare the SSH host fingerprint out of band;
3. enroll it in the project-local `.ssh/known_hosts`;
4. run read-only discovery;
5. copy the repository without secrets.

```bash
EXPECTED_FINGERPRINT=SHA256:... make ssh-scan-host
INFERENCE_ALLOW_REMOTE=1 make preflight-remote
INFERENCE_ALLOW_REMOTE=1 make sync-remote
```

Stop if GPU count/VRAM, disk, RAM, driver, runtime, or model fit disagrees with
the chosen profile.

## 4. Start the Compose service on the GPU host

On the Linux NVIDIA host, create its gitignored `.env.local`, then:

```bash
make compose-env-check PROFILE=vast-k3s-replica
make phase1-build PHASE1_PROFILE=vast-k3s-replica
make phase1-up PHASE1_PROFILE=vast-k3s-replica
```

If Docker cannot select a GPU although it lists an NVIDIA runtime, follow the
Docker-specific NVIDIA Toolkit/CDI fix in
[Troubleshooting](troubleshooting.md). Do not rewrite a k3s containerd template.

Verify on the GPU host:

```bash
make health
docker compose --project-directory . -f docker/compose.yaml \
  --env-file artifacts/compose.env ps
```

The published listener must be `127.0.0.1:8000`, never a public
`0.0.0.0:8000` bind.

## 5. Open the private client path

On the Mac, set:

```text
VLLM_REMOTE_HOST=127.0.0.1
VLLM_REMOTE_PORT=8000
VLLM_LOCAL_TUNNEL_PORT=8000
VLLM_BASE_URL=http://127.0.0.1:8000
```

Then:

```bash
make tunnel
make health
INFERENCE_PROFILE=vast-k3s-replica make test-phase1
```

The acceptance test requires 10 concurrent streams with non-empty output,
terminal state, and `data: [DONE]`.

## 6. Call it from a personal application

Any OpenAI-compatible client can target:

```text
base URL: http://127.0.0.1:8000/v1
model:    qwen2.5-1.5b-instruct-awq
```

Example request:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-1.5b-instruct-awq",
    "messages": [{"role": "user", "content": "Summarize my notes in five bullets."}],
    "stream": false,
    "max_tokens": 128
  }'
```

Because the URL is workstation loopback forwarded through SSH, the raw vLLM
port is not public. Add an API key if multiple local applications share the
tunnel, but remember that vLLM's key may not protect health and metrics.

## 7. Personal feature ideas

### Notes and document assistant

Keep documents in your local application, select only relevant passages, and
send those passages in the prompt. Add a local vector index later if retrieval
is needed; vLLM remains the generation server.

### Structured extraction

Ask for a small JSON object and validate it in the client. Keep retries and
schema repair in the application rather than changing the serving layer.

### Batch summarization

Use bounded concurrency and record failures in the denominator. The existing
benchmark/load clients demonstrate safe concurrency and timeouts.

### Private home API

Keep the service on loopback and use SSH from the device that needs it. If the
service must be reachable from the Internet, move to the production security
goals first: verified TLS, authentication, rate limits, and an HA gateway.

### Learning observability

Move to Stage 4 of the [Feature pathway](feature-pathway.md) to inspect token
throughput, running/waiting requests, KV-cache utilization, TTFT, and E2E.

## Cost controls

- Rent on demand and record the hourly compute and storage rate before launch.
- Use the 1.5B AWQ model for most experiments.
- Reuse the model cache while the VM is alive.
- Avoid k3s/Prometheus/KEDA unless their behavior is the goal.
- Set a calendar/session stop time.
- Stop the workload first, confirm no listener/GPU process, then delete the VM.
- Verify the provider reports zero active instances.

Scale-to-zero removes the vLLM GPU process while the VM and control plane still
exist. It does not stop provider VM billing. Destroying the rental is the
reliable end-of-session cost control.

## Shutdown checklist

1. Stop clients and drain requests.
2. Close the exact SSH tunnel process with SIGTERM.
3. On the GPU host:

   ```bash
   make phase1-down PHASE1_PROFILE=vast-k3s-replica
   ```

4. Confirm no Compose container, `:8000` listener, or GPU compute process.
5. Delete the rental through the provider.
6. Confirm the deletion response/UI and later connection failure.

The Git repository remains the source of truth. Rental model caches and logs
are disposable.

## When to add Kubernetes

Use Kubernetes when you specifically want:

- health-driven routing and automatic pod recovery;
- GPU resource scheduling;
- stable Services and per-replica PVCs;
- Prometheus ServiceMonitor discovery;
- KEDA replica autoscaling;
- scale-to-zero experiments.

For a single personal endpoint, Compose usually provides the same model API
with less memory use and fewer moving parts.

See [Feature pathway](feature-pathway.md) for the progression from personal
Compose to the full platform.
