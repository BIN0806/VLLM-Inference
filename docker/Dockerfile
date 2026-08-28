# Thin wrapper around the official pinned vLLM OpenAI server image.
# Do not rebuild CUDA or vLLM from source unless a later phase proves it is required.
# Secrets and model weights are not included.

ARG VLLM_IMAGE=vllm/vllm-openai:v0.27.1@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2
FROM ${VLLM_IMAGE}

LABEL org.opencontainers.image.title="inference-platform-vllm"
LABEL org.opencontainers.image.description="Pinned vLLM OpenAI-compatible inference server"
LABEL org.opencontainers.image.source="https://github.com/example/inference-platform"
LABEL org.opencontainers.image.version="0.27.1"

# Upstream entrypoint is preserved (vLLM OpenAI API server).
