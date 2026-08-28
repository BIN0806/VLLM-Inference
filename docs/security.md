# Security

- Never commit `VLLM_API_KEY`, `HF_TOKEN`, `OPEN_BUTTON_TOKEN`, Vast API keys, GitHub credentials, kubeconfigs, or private keys.
- `.env.example` contains placeholders only. Live values live in gitignored `.env.local`.
- Authentication is optional for SSH-tunneled testing. `VLLM_API_KEY` does **not** protect every vLLM endpoint (health and metrics may remain unauthenticated). Any host-network or public exposure needs an authenticating reverse proxy or firewall in front of vLLM. The Vast portal's authenticated reverse proxy is the current external boundary.
- Compose publishes ports on `127.0.0.1` by default (`HOST_BIND`). Do not bind raw vLLM to `0.0.0.0` on the host unless a later production overlay adds that proxy. The in-container process may listen on `0.0.0.0`; that is not the published bind.
- SSH uses the existing agent. Tooling never reads or copies private-key contents. Host-key checking stays enabled (`StrictHostKeyChecking=yes`).
- First contact (`make ssh-scan-host`) captures a **candidate** key in a temporary file, prints the SHA256 fingerprint, and installs it only after `EXPECTED_FINGERPRINT=SHA256:...`, a matching fingerprint in a trusted `known_hosts` file, or `CONFIRM=yes`. It does not append `ssh-keyscan` output to `known_hosts` as if it were already verified. Keys are stored in the gitignored project file `.ssh/known_hosts` so Vast rentals do not pollute `~/.ssh/known_hosts`.
- This GitHub repository is public. Never commit live SSH hosts, instance IDs, `.env.local`, private keys, `known_hosts`, Hugging Face tokens, or API keys. The implementation blueprint is gitignored.
- Do not disable TLS verification against production endpoints. `VLLM_TLS_VERIFY` defaults to true.
- `trust_remote_code` stays false unless a later ADR records a proven requirement for a specific model.
- Preflight and reports redact secret names and values.
- The current Vast filesystem is ephemeral. Do not store the only copy of source there.
- Do not create, stop, restart, or destroy Vast instances from this repository.
