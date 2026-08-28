# Security

- Never commit `VLLM_API_KEY`, `HF_TOKEN`, `OPEN_BUTTON_TOKEN`, Vast API keys, GitHub credentials, kubeconfigs, or private keys.
- `.env.example` contains placeholders only. Live values live in gitignored `.env.local`.
- Authentication is optional for SSH-tunneled testing and required for any externally exposed Vast endpoint and future production overlays. Tests must support both.
- SSH uses the existing agent. Tooling never reads or copies private-key contents. Host-key checking stays enabled (`StrictHostKeyChecking=yes`). First contact uses `make ssh-scan-host`.
- Do not disable TLS verification against production endpoints. `VLLM_TLS_VERIFY` defaults to true.
- `trust_remote_code` stays false unless a later ADR records a proven requirement for a specific model.
- Preflight and reports redact secret names and values.
- The current Vast filesystem is ephemeral. Do not store the only copy of source there.
- Do not create, stop, restart, or destroy Vast instances from this repository.
