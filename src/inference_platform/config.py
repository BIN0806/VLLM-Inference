"""Layered configuration loaded from YAML plus environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from inference_platform.paths import configs_dir, default_known_hosts_path
from inference_platform.ssh import SSHTarget

SECRET_SETTING_NAMES = frozenset({"vllm_api_key", "hf_token", "open_button_token"})


def load_local_env() -> None:
    """Load gitignored env files into os.environ without overriding already-set values."""
    from inference_platform.paths import repo_root

    root = repo_root()
    for name in (".env.local", ".env"):
        path = root / name
        if path.is_file():
            load_dotenv(path, override=False)


class ModelConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    role: str
    model_id: str
    revision: str
    served_model_name: str
    license: str
    license_url: str | None = None
    source_url: str | None = None
    quantization: str = "none"
    dtype: str = "auto"
    trust_remote_code: bool = False
    architecture: str | None = None
    parameter_count: int | None = None
    weight_gib: float
    estimated_min_vram_gib: float
    kv_cache_mib_per_1k_tokens: float | None = None
    used_storage_gib: float | None = None
    notes: str | None = None
    headroom_note: str | None = None


class ComputeConfig(BaseModel):
    id: str
    description: str | None = None
    gpus_per_replica: int = 1
    tensor_parallel_size: int = 1
    pipeline_parallel_size: int = 1
    distributed_executor_backend: Literal["mp", "ray"] = "mp"
    replica_count: int = 1
    min_replicas: int | None = None
    max_replicas: int | None = None
    scaling_unit: Literal["complete-replica"] = "complete-replica"
    horizontal_scaling: bool = False
    requires_nodes: int = 1
    scaler: str | None = None
    requires_durable_interceptor: bool = False
    status: str | None = None
    notes: str | None = None

    @field_validator(
        "gpus_per_replica",
        "tensor_parallel_size",
        "pipeline_parallel_size",
        "replica_count",
        "requires_nodes",
    )
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("numeric topology fields must be >= 1")
        return value


class ServingConfig(BaseModel):
    host: str = "0.0.0.0"
    host_bind: str = "127.0.0.1"
    container_port: int = 8000
    host_port: int = 8000
    gpu_memory_utilization: float = 0.90
    max_model_len: int = 8192
    max_num_seqs: int = 8
    trust_remote_code: bool = False
    enable_prefix_caching: bool = False
    dtype: str = "auto"
    kv_cache_dtype: str = "auto"
    shm_size: str = "8g"
    health_path: str = "/health"
    metrics_path: str = "/metrics"
    openai_prefix: str = "/v1"
    request_timeout_seconds: int = 120
    notes: str | None = None

    @field_validator("gpu_memory_utilization")
    @classmethod
    def _util(cls, value: float) -> float:
        if not 0.1 <= value <= 0.99:
            raise ValueError("gpu_memory_utilization must be between 0.1 and 0.99")
        return value

    @field_validator("max_model_len", "max_num_seqs", "request_timeout_seconds")
    @classmethod
    def _positive_serving(cls, value: int) -> int:
        if value < 1:
            raise ValueError("serving numeric fields must be >= 1")
        return value


class WorkloadConfig(BaseModel):
    id: str
    classification: str
    production_slo: bool = False
    streaming: bool = True
    typical_prompt_tokens: int
    requested_output_tokens: int
    concurrency_levels: list[int]
    phase1_acceptance_concurrency: int = 10
    warmup_requests: int = 4
    warmup_duration_seconds: int = 30
    measurement_duration_seconds: int = 60
    request_timeout_seconds: int = 120
    success_definition: str | None = None
    prompt_template: str | None = None
    topics: list[str] = Field(default_factory=list)
    optional_scenarios: dict[str, dict[str, int]] = Field(default_factory=dict)
    notes: str | None = None


class ProfileConfig(BaseModel):
    id: str
    provider: str
    compute: str | None = None
    model: str
    fallback_model: str | None = None
    serving: str = "defaults"
    workload: str = "dev-smoke"
    gpu_required: bool = False
    remote_required: bool = False
    hardware_source: str | None = None
    notes: str | None = None


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    gpu_provider: str | None = None
    gpu_ssh_host: str | None = None
    gpu_ssh_port: int | None = None
    gpu_ssh_user: str = "root"
    gpu_instance_id: str | None = None
    gpu_ssh_identity_file: Path | None = None
    gpu_ssh_known_hosts: Path | None = None
    gpu_ssh_connect_timeout: int = 15
    gpu_ssh_strict_host_key_checking: str = "yes"

    vllm_base_url: str = "http://127.0.0.1:8000"
    vllm_remote_host: str = "127.0.0.1"
    vllm_remote_port: int = 18000
    vllm_local_tunnel_port: int = 8000
    host_bind: str = "127.0.0.1"
    vllm_tls_verify: bool = True
    vllm_api_key: str | None = None
    open_button_token: str | None = None
    vllm_image: str | None = None
    vllm_tensor_parallel_size: int | None = None
    vllm_pipeline_parallel_size: int | None = None
    vllm_max_model_len: int | None = None
    vllm_max_num_seqs: int | None = None
    vllm_gpu_memory_utilization: float | None = None
    distributed_executor_backend: str | None = None
    vllm_model: str | None = None
    served_model_name: str | None = None
    model_revision: str | None = None
    hf_home: str | None = None
    hf_token: str | None = None
    hf_hub_disable_xet: bool = True

    compute_profile: str | None = None
    model_config_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MODEL_CONFIG", "model_config_name"),
    )
    workload_scenario: str = "dev-smoke"

    allow_tp_fallback: bool = False
    allow_model_fallback: bool = False
    allow_offline_test_fallback: bool = False
    inference_allow_remote: bool = False
    allow_insecure_remote_http: bool = False

    k8s_namespace: str = "inference"
    k8s_pvc_size: str | None = None
    k8s_storage_class: str = "local-path"
    k8s_model_cache_path: str | None = None
    k8s_cpu_request: str = "2"
    k8s_memory_request: str = "8Gi"

    @field_validator(
        "gpu_ssh_port",
        "vllm_tensor_parallel_size",
        "vllm_pipeline_parallel_size",
        "vllm_max_model_len",
        "vllm_max_num_seqs",
        "vllm_gpu_memory_utilization",
        "gpu_ssh_identity_file",
        "gpu_ssh_known_hosts",
        "vllm_image",
        "vllm_model",
        "served_model_name",
        "model_revision",
        "hf_home",
        "hf_token",
        "vllm_api_key",
        "open_button_token",
        "gpu_provider",
        "gpu_ssh_host",
        "gpu_instance_id",
        "distributed_executor_backend",
        "compute_profile",
        "model_config_name",
        "k8s_pvc_size",
        "k8s_model_cache_path",
        mode="before",
    )
    @classmethod
    def _empty_str_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def _fill_api_key_from_vast_open_button(self) -> EnvSettings:
        """SSH tunnels skip Caddy. Public mapped ports need OPEN_BUTTON_TOKEN."""
        if not self.vllm_api_key and self.open_button_token:
            self.vllm_api_key = self.open_button_token
        return self


class ResolvedConfig(BaseModel):
    profile: ProfileConfig
    compute: ComputeConfig | None
    model: ModelConfig
    fallback_model: ModelConfig | None = None
    serving: ServingConfig
    workload: WorkloadConfig
    env: EnvSettings
    pins: dict[str, Any]

    @property
    def tensor_parallel_size(self) -> int:
        if self.env.vllm_tensor_parallel_size is not None:
            return self.env.vllm_tensor_parallel_size
        if self.compute is None:
            return 1
        return self.compute.tensor_parallel_size

    @property
    def pipeline_parallel_size(self) -> int:
        if self.env.vllm_pipeline_parallel_size is not None:
            return self.env.vllm_pipeline_parallel_size
        if self.compute is None:
            return 1
        return self.compute.pipeline_parallel_size

    @property
    def distributed_executor_backend(self) -> str:
        if self.env.distributed_executor_backend:
            return self.env.distributed_executor_backend
        if self.compute is None:
            return "mp"
        return self.compute.distributed_executor_backend

    @property
    def model_id(self) -> str:
        return self.env.vllm_model or self.model.model_id

    @property
    def served_name(self) -> str:
        return self.env.served_model_name or self.model.served_model_name

    @property
    def revision(self) -> str:
        return self.env.model_revision or self.model.revision

    @property
    def max_model_len(self) -> int:
        return self.env.vllm_max_model_len or self.serving.max_model_len

    @property
    def max_num_seqs(self) -> int:
        return self.env.vllm_max_num_seqs or self.serving.max_num_seqs

    @property
    def gpu_memory_utilization(self) -> float:
        return self.env.vllm_gpu_memory_utilization or self.serving.gpu_memory_utilization

    def vllm_image_ref(self) -> str:
        if self.env.vllm_image:
            return self.env.vllm_image
        image = self.pins.get("vllm", {}).get("official_image", {})
        ref = image.get("ref")
        if ref:
            return str(ref)
        raise ValueError("vLLM image digest is not pinned")

    def model_cache_path(self) -> str:
        return self.env.k8s_model_cache_path or self.env.hf_home or "/root/.cache/huggingface"

    def pvc_size(self) -> str:
        if self.env.k8s_pvc_size:
            return self.env.k8s_pvc_size
        storage = self.model.used_storage_gib or self.model.weight_gib
        gib = max(40, int(storage) + 20)
        return f"{gib}Gi"

    def ssh_target(self) -> SSHTarget:
        if not self.env.gpu_ssh_host or self.env.gpu_ssh_port is None:
            raise ValueError("GPU_SSH_HOST and GPU_SSH_PORT are required for SSH")
        return SSHTarget(
            host=self.env.gpu_ssh_host,
            port=self.env.gpu_ssh_port,
            user=self.env.gpu_ssh_user,
            known_hosts=self.env.gpu_ssh_known_hosts or default_known_hosts_path(),
            identity_file=self.env.gpu_ssh_identity_file,
            connect_timeout=self.env.gpu_ssh_connect_timeout,
            strict_host_key_checking=self.env.gpu_ssh_strict_host_key_checking,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.id,
            "provider": self.env.gpu_provider or self.profile.provider,
            "compute": None if self.compute is None else self.compute.model_dump(),
            "model_id": self.model_id,
            "model_revision": self.revision,
            "served_model_name": self.served_name,
            "fallback_model": None if self.fallback_model is None else self.fallback_model.model_id,
            "tensor_parallel_size": self.tensor_parallel_size,
            "pipeline_parallel_size": self.pipeline_parallel_size,
            "distributed_executor_backend": self.distributed_executor_backend,
            "max_model_len": self.max_model_len,
            "max_num_seqs": self.max_num_seqs,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "vllm_image": self.env.vllm_image,
            "vllm_base_url": self.env.vllm_base_url,
            "workload": self.workload.id,
            "allow_tp_fallback": self.env.allow_tp_fallback,
            "allow_model_fallback": self.env.allow_model_fallback,
            "allow_offline_test_fallback": self.env.allow_offline_test_fallback,
            "allow_insecure_remote_http": self.env.allow_insecure_remote_http,
        }


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def _load_named(kind: str, name: str, model_type: type):
    path = configs_dir() / kind / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown {kind} config {name!r} ({path})")
    return model_type.model_validate(load_yaml(path))


def load_pins() -> dict[str, Any]:
    return load_yaml(configs_dir() / "pins.yaml")


def load_profile(profile_id: str, env: EnvSettings | None = None) -> ResolvedConfig:
    env = env or EnvSettings()
    profile = _load_named("profiles", profile_id, ProfileConfig)
    compute = None
    compute_name = env.compute_profile or profile.compute
    if compute_name:
        compute = _load_named("compute", compute_name, ComputeConfig)
    model_name = env.model_config_name or profile.model
    model = _load_named("models", model_name, ModelConfig)
    fallback = None
    if profile.fallback_model:
        fallback = _load_named("models", profile.fallback_model, ModelConfig)
    serving_name = profile.serving
    serving = ServingConfig.model_validate(
        load_yaml(configs_dir() / "serving" / f"{serving_name}.yaml")
    )
    workload_name = env.workload_scenario or profile.workload
    workload = _load_named("workloads", workload_name, WorkloadConfig)
    if env.vllm_max_model_len:
        serving = serving.model_copy(update={"max_model_len": env.vllm_max_model_len})
    if env.vllm_max_num_seqs:
        serving = serving.model_copy(update={"max_num_seqs": env.vllm_max_num_seqs})
    if env.vllm_gpu_memory_utilization is not None:
        serving = serving.model_copy(
            update={"gpu_memory_utilization": env.vllm_gpu_memory_utilization}
        )
    return ResolvedConfig(
        profile=profile,
        compute=compute,
        model=model,
        fallback_model=fallback,
        serving=serving,
        workload=workload,
        env=env,
        pins=load_pins(),
    )


def default_profile_id() -> str:
    return os.environ.get("INFERENCE_PROFILE", "authoring")
