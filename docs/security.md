# Security

- Never commit `VLLM_API_KEY`, `HF_TOKEN`, `OPEN_BUTTON_TOKEN`, Vast API keys, GitHub credentials, kubeconfigs, or private keys.
- `.env.example` contains placeholders only. Live values live in gitignored `.env.local`.
- Authentication is optional for SSH-tunneled testing. An SSH local-forward to remote `127.0.0.1:18000` skips Vast Caddy.
- Bearer authentication without TLS does **not** protect token or prompt confidentiality. An on-path observer can read both. A one-time Phase 1 public-HTTP Bearer call was a development diagnostic of Caddy's authentication mechanics only; it is not secure production exposure. Treat that instance token as potentially exposed. Destroying the temporary Vast instance retires the instance-specific token.
- The HTTP client refuses to send `VLLM_API_KEY` or `OPEN_BUTTON_TOKEN` to a non-loopback `http://` URL unless `ALLOW_INSECURE_REMOTE_HTTP=true`. That override is lab-only and defaults to false. Loopback addresses used through SSH tunnels may continue using HTTP. Future testing must use an SSH tunnel or properly configured HTTPS.
- `VLLM_API_KEY` does **not** protect every vLLM endpoint (health and metrics may remain unauthenticated on the process itself). Any host-network or public exposure needs an authenticating reverse proxy **and** TLS, or a firewall in front of vLLM.
- Compose publishes ports on `127.0.0.1` by default (`HOST_BIND`). Do not bind raw vLLM to `0.0.0.0` on the host unless a later production overlay adds that proxy. The in-container process may listen on `0.0.0.0`; that is not the published bind.
- SSH uses the existing agent. Tooling never reads or copies private-key contents. Host-key checking stays enabled (`StrictHostKeyChecking=yes`).
- First contact (`make ssh-scan-host`) captures a **candidate** key in a temporary file, prints the SHA256 fingerprint, and installs it only after `EXPECTED_FINGERPRINT=SHA256:...`, a matching fingerprint in a trusted `known_hosts` file, or `CONFIRM=yes`. It does not append `ssh-keyscan` output to `known_hosts` as if it were already verified. Keys are stored in the gitignored project file `.ssh/known_hosts` so Vast rentals do not pollute `~/.ssh/known_hosts`.
- This GitHub repository is public. Never commit live SSH hosts, instance IDs, `.env.local`, private keys, `known_hosts`, Hugging Face tokens, or API keys. The implementation blueprint is gitignored.
- Do not disable TLS verification against production endpoints. `VLLM_TLS_VERIFY` defaults to true.
- **Security backlog (does not block Phase 2):** remote HTTPS clients must refuse to send `VLLM_API_KEY` or `OPEN_BUTTON_TOKEN` when `VLLM_TLS_VERIFY=false`, unless a prominent lab-only override is explicitly enabled. Phase 2 uses a loopback SSH tunnel, so this is not a Phase 2A gate.
- `trust_remote_code` stays false unless a later ADR records a proven requirement for a specific model.
- Preflight and reports redact secret names and values.
- The current Vast filesystem is ephemeral. Do not store the only copy of source there.
- Do not create, stop, restart, or destroy Vast instances from this repository.
- Phase 3 Kubernetes YAML is rendered offline. Do not `kubectl apply`, install k3s, or rent hardware until explicitly approved. The first gate uses SSH-tunneled loopback, not a public vLLM URL.
