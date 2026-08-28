# KEDA (not deployed in Phase 0)

Pinned:

- KEDA 2.20.2
- KEDA HTTP Add-on 0.15.0

Rules already decided:

- Scale complete replicas only.
- First Kubernetes MVP: minReplicas=1, scale on waiting work / gateway concurrency.
- Scale-to-zero is a later profile and **must** use the HTTP add-on interceptor (or an approved equivalent). vLLM metrics cannot wake zero replicas.
- Do not attach a Deployment scaler to individual KubeRay workers.
