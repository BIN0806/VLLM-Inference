"""Compose interpolation and profile agreement. Does not require a Docker daemon."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from inference_platform.config import ResolvedConfig, load_local_env, load_profile
from inference_platform.paths import artifacts_dir, repo_root
from inference_platform.secrets import redact_mapping


class ComposeProfileMismatch(ValueError):
    """Raised when the selected profile and Compose interpolation would disagree."""


def interpolate(value: str, env: dict[str, str]) -> str:
    """Expand Compose-style ${VAR} and ${VAR:-default}, including nested defaults."""

    out: list[str] = []
    index = 0
    while index < len(value):
        if value.startswith("${", index):
            expr, index = _read_braced(value, index + 2)
            out.append(_eval_expression(expr, env))
        else:
            out.append(value[index])
            index += 1
    return "".join(out)


def _read_braced(value: str, index: int) -> tuple[str, int]:
    depth = 1
    start = index
    while index < len(value) and depth:
        if value.startswith("${", index):
            depth += 1
            index += 2
            continue
        if value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[start:index], index + 1
        index += 1
    raise ValueError(f"Unbalanced interpolation in {value!r}")


def _eval_expression(expr: str, env: dict[str, str]) -> str:
    if ":-" in expr:
        name, default = expr.split(":-", 1)
        current = env.get(name.strip(), "")
        if current:
            return current
        return interpolate(default, env)
    return env.get(expr.strip(), "")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, remainder = line.partition("=")
        values[key.strip()] = remainder.strip().strip("'").strip('"')
    return values


def load_compose_document(path: Path | None = None) -> dict[str, Any]:
    compose_path = path or repo_root() / "docker" / "compose.yaml"
    with compose_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{compose_path} must contain a mapping")
    return data


def flag_value(command: list[str], flag: str) -> str | None:
    try:
        index = command.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return command[index + 1]


def profile_compose_vars(config: ResolvedConfig) -> dict[str, str]:
    bind = config.env.host_bind or config.serving.host_bind
    return {
        "VLLM_MODEL": config.model_id,
        "MODEL_PATH": config.model_id,
        "MODEL_REVISION": config.revision,
        "SERVED_MODEL_NAME": config.served_name,
        "VLLM_TENSOR_PARALLEL_SIZE": str(config.tensor_parallel_size),
        "VLLM_PIPELINE_PARALLEL_SIZE": str(config.pipeline_parallel_size),
        "VLLM_MAX_MODEL_LEN": str(config.max_model_len),
        "VLLM_MAX_NUM_SEQS": str(config.max_num_seqs),
        "VLLM_GPU_MEMORY_UTILIZATION": str(config.gpu_memory_utilization),
        "DISTRIBUTED_EXECUTOR_BACKEND": config.distributed_executor_backend,
        "HOST_BIND": bind,
        "HOST_PORT": str(config.serving.host_port),
        "CONTAINER_PORT": str(config.serving.container_port),
        "HF_HUB_DISABLE_XET": "1" if config.env.hf_hub_disable_xet else "0",
    }


def merge_compose_env(config: ResolvedConfig, file_env: dict[str, str]) -> dict[str, str]:
    merged = dict(file_env)
    conflicts: list[str] = []
    for key, profile_value in profile_compose_vars(config).items():
        file_value = file_env.get(key, "")
        if file_value and file_value != profile_value:
            conflicts.append(f"{key}: env={file_value!r} profile={profile_value!r}")
        merged[key] = file_value or profile_value
    if config.env.vllm_api_key:
        merged.setdefault("VLLM_API_KEY", config.env.vllm_api_key)
    if config.env.vllm_image:
        merged.setdefault("VLLM_IMAGE", config.env.vllm_image)
    if conflicts:
        raise ComposeProfileMismatch(
            "Profile and Compose environment disagree; refusing silent mismatch: "
            + "; ".join(conflicts)
        )
    return merged


def render_vllm_service(
    env: dict[str, str], *, compose_doc: dict[str, Any] | None = None
) -> dict[str, Any]:
    document = compose_doc or load_compose_document()
    service = document["services"]["vllm"]
    command = [
        interpolate(item, env) if isinstance(item, str) else item for item in service["command"]
    ]
    ports = [
        interpolate(item, env) if isinstance(item, str) else item
        for item in service.get("ports", [])
    ]
    environment = {
        key: interpolate(str(value), env)
        for key, value in (service.get("environment") or {}).items()
    }
    return {
        "command": command,
        "ports": ports,
        "environment": environment,
        "container_name": service.get("container_name"),
        "model": flag_value(command, "--model"),
        "revision": flag_value(command, "--revision"),
        "tensor_parallel_size": flag_value(command, "--tensor-parallel-size"),
        "max_model_len": flag_value(command, "--max-model-len"),
        "api_key": environment.get("VLLM_API_KEY"),
    }


def validate_rendered_service(config: ResolvedConfig, rendered: dict[str, Any]) -> None:
    problems: list[str] = []
    if rendered["model"] != config.model_id:
        problems.append(f"model compose={rendered['model']!r} profile={config.model_id!r}")
    if rendered["revision"] != config.revision:
        problems.append(f"revision compose={rendered['revision']!r} profile={config.revision!r}")
    if rendered["tensor_parallel_size"] != str(config.tensor_parallel_size):
        problems.append(
            f"tp compose={rendered['tensor_parallel_size']!r} profile={config.tensor_parallel_size!r}"
        )
    if rendered["max_model_len"] != str(config.max_model_len):
        problems.append(
            f"max_model_len compose={rendered['max_model_len']!r} profile={config.max_model_len!r}"
        )
    if rendered.get("container_name"):
        problems.append("container_name is set; it blocks Compose replica scaling")
    bind = config.env.host_bind or config.serving.host_bind
    if not any(
        str(port).startswith(f"{bind}:") or str(port).startswith("127.0.0.1:")
        for port in rendered["ports"]
    ):
        if bind == "127.0.0.1":
            problems.append(f"published ports {rendered['ports']!r} are not bound to {bind}")
    if problems:
        raise ComposeProfileMismatch("; ".join(problems))


def write_export_file(path: Path, env: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}\n" for key, value in sorted(env.items())]
    path.write_text("".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose/profile agreement helper")
    parser.add_argument("action", choices=["check", "export"])
    parser.add_argument("--profile", default="vast-single-gpu")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    env_path = Path(args.env_file)
    if not env_path.is_file():
        print(
            f"error: {env_path} is missing. Copy .env.example to .env.local. "
            "Compose interpolation does not read the service env_file: mapping.",
            file=sys.stderr,
        )
        return 1
    load_local_env()
    config = load_profile(args.profile)
    file_env = parse_env_file(env_path)
    try:
        merged = merge_compose_env(config, file_env)
        rendered = render_vllm_service(merged)
        validate_rendered_service(config, rendered)
    except ComposeProfileMismatch as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    public = redact_mapping(
        {
            "profile": config.profile.id,
            "model": rendered["model"],
            "revision": rendered["revision"],
            "tensor_parallel_size": rendered["tensor_parallel_size"],
            "max_model_len": rendered["max_model_len"],
            "ports": rendered["ports"],
            "api_key_set": bool(rendered["api_key"]),
        }
    )
    if args.action == "export":
        out = Path(args.out) if args.out else artifacts_dir() / "compose.env"
        write_export_file(out, merged)
        print(f"wrote {out}")
    print(public)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
