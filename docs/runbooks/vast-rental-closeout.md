# Vast rental closeout (Phase 4 lab VM)

Sanitized teardown of the single-node Phase 4 lab rental. No IP addresses,
SSH ports, host keys, tokens, credentials, instance IDs, kubeconfigs, or raw
cluster dumps are recorded here.

Destroy of the vendor instance is an **operator** action (Vast CLI or
console), not repository tooling. This file records the sanitized result.

**Phase 4A, 4B, and 4C remain GO.** Compose 1.5B on GPU 0 is GO
([compose-1.5b-status.md](compose-1.5b-status.md)). HTTP **0→2** was not
tested.

## Final Kubernetes / KEDA inventory (before k3s stop)

Captured while k3s was still running, after the accepted Phase 4C gate:

| Object | State |
|---|---|
| StatefulSet `vllm` | **0/0** |
| PVCs `model-cache-vllm-0` and `model-cache-vllm-1` | **Bound** (local-path) |
| HTTP ScaledObject `vllm` | `external-push`, min=0, max=2, `interceptorRoute: vllm` |
| InterceptorRoute `vllm` | Ready |
| HTTPScaledObject objects | **0** |
| KEDA / HTTP add-on / Prometheus | Ready (control plane still up) |
| GPUs | both idle (0 MiB) |

kube-apiserver stayed firewalled to loopback and cluster-internal ranges.
No Ingress, NodePort, LoadBalancer, or public TLS was installed.

## Stop order (no SIGKILL)

1. Closed Kubernetes port-forwards with **SIGTERM** on the exact `kubectl`
   PIDs. Do not `pkill -f port-forward`; that string also matches the SSH
   remote command and can kill the session.
2. `systemctl stop k3s`. Unit became **inactive**. No k3s process remained.
   The apiserver listener closed. Both GPUs stayed idle.
3. `k3s-killall.sh` was **not** used.
4. Docker Compose 1.5B validation ran on GPU 0, then
   `docker compose … down` (see the Compose report).
5. Vendor instance destroy is recorded below.

`local-path` PVCs and Hugging Face caches live on the VM disk. They do **not**
survive vendor destroy.

## Vendor destroy

**Status: instance deleted.** The operator sent `DELETE` to the Vast
instances API using the VM-scoped container key. The API returned HTTP
**200** with `success: true`. A later SSH attempt to the former rental
**timed out**. No instance IDs, hosts, or API keys are recorded here.

VM-local k3s `local-path` PVCs, Hugging Face caches, and the Compose
`HF_HOME` bind-mount copy **died with the VM**. They are not
provider-persistent volumes.

Authoring-host follow-up: SSH tunnels were closed with SIGTERM; no local
`:8000` listener and no remaining `ssh -L` forwards.

## Claim boundary after closeout

Completed and still claimed: serving-only pins; concurrent SSE; 9B TP=2 on
a different host; same-host Ray; Phase 3–4C k3s/KEDA/HTTP lab proofs;
Compose 1.5B loopback validation.

Still untested: HTTP 0→2, interceptor HA, public TLS, multi-node Ray,
managed Kubernetes, 9B autoscaling, 5,000 output tokens/s.
