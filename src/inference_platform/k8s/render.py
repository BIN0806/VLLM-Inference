"""Render provider-neutral Kubernetes manifests from a composed profile.

Does not talk to a cluster. Does not install k3s, the NVIDIA toolkit, or the
device plugin. Fail closed if the selected compute topology is not a single
warm mp replica.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

from inference_platform.config import (
    ResolvedConfig,
    default_profile_id,
    load_local_env,
    load_profile,
)
from inference_platform.paths import repo_root
from inference_platform.topology import validate_topology


class RenderError(ValueError):
    """Raised when the selected profile cannot be rendered as the Phase 3 replica."""


def _probe(path: str, port: int) -> dict[str, Any]:
    return {
        "httpGet": {"path": path, "port": port},
        "timeoutSeconds": 5,
    }


def default_pvc_size(config: ResolvedConfig) -> str:
    return config.pvc_size()


def vllm_args(config: ResolvedConfig) -> list[str]:
    args = [
        "--model",
        config.model_id,
        "--revision",
        config.revision,
        "--served-model-name",
        config.served_name,
        "--tensor-parallel-size",
        str(config.tensor_parallel_size),
        "--pipeline-parallel-size",
        str(config.pipeline_parallel_size),
        "--distributed-executor-backend",
        config.distributed_executor_backend,
        "--gpu-memory-utilization",
        str(config.gpu_memory_utilization),
        "--max-model-len",
        str(config.max_model_len),
        "--max-num-seqs",
        str(config.max_num_seqs),
        "--host",
        "0.0.0.0",
        "--port",
        str(config.serving.container_port),
    ]
    quant = (config.model.quantization or "none").lower()
    if quant not in {"", "none"}:
        args.extend(["--quantization", quant])
    return args


def _validate_renderable(config: ResolvedConfig) -> None:
    compute = config.compute
    if compute is None or compute.id not in {"k8s-replica", "k8s-replica-zero"}:
        raise RenderError("Kubernetes render requires compute profile k8s-replica")
    if compute.id == "k8s-replica-zero":
        raise RenderError("k8s-replica-zero is a later gate; render the warm replica only")
    report = validate_topology(config, None)
    fails = [issue for issue in report.issues if issue.severity == "FAIL"]
    if fails:
        raise RenderError(fails[0].message)
    if config.tensor_parallel_size != 1 or config.pipeline_parallel_size != 1:
        raise RenderError("Phase 3 render requires TP=1 and PP=1")
    if config.distributed_executor_backend != "mp":
        raise RenderError("Phase 3 render refuses Ray; use mp")
    if config.env.allow_model_fallback:
        raise RenderError("Refusing to render while ALLOW_MODEL_FALLBACK is enabled")
    if config.env.allow_tp_fallback:
        raise RenderError("Refusing to render while ALLOW_TP_FALLBACK is enabled")


def render_manifests(config: ResolvedConfig) -> dict[str, dict[str, Any]]:
    """Return filename -> Kubernetes object. Secret is a template with empty values."""

    _validate_renderable(config)
    namespace = config.env.k8s_namespace
    port = config.serving.container_port
    cache = config.model_cache_path()
    image = config.vllm_image_ref()
    plugin = config.pins.get("charts_and_operators", {}).get("nvidia_device_plugin", "0.20.0")
    labels = {"app": "inference-platform", "component": "vllm"}
    args = vllm_args(config)

    namespace_doc = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": namespace, "labels": {"app": "inference-platform"}},
    }
    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "vllm-serving", "namespace": namespace, "labels": labels},
        "data": {
            "MODEL_ID": config.model_id,
            "MODEL_REVISION": config.revision,
            "SERVED_MODEL_NAME": config.served_name,
            "QUANTIZATION": config.model.quantization,
            "DTYPE": config.model.dtype,
            "TENSOR_PARALLEL_SIZE": str(config.tensor_parallel_size),
            "PIPELINE_PARALLEL_SIZE": str(config.pipeline_parallel_size),
            "DISTRIBUTED_EXECUTOR_BACKEND": config.distributed_executor_backend,
            "GPU_MEMORY_UTILIZATION": str(config.gpu_memory_utilization),
            "MAX_MODEL_LEN": str(config.max_model_len),
            "MAX_NUM_SEQS": str(config.max_num_seqs),
            "MODEL_CACHE_PATH": cache,
            "CONTAINER_PORT": str(port),
            "VLLM_IMAGE": image,
            "NVIDIA_DEVICE_PLUGIN": str(plugin),
            "STORAGE_CLASS": config.env.k8s_storage_class,
            "PVC_SIZE": default_pvc_size(config),
            "HF_HUB_DISABLE_XET": "1" if config.env.hf_hub_disable_xet else "0",
        },
    }
    storage = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "vllm-storage", "namespace": namespace, "labels": labels},
        "data": {
            "storageClassName": config.env.k8s_storage_class,
            "accessMode": "ReadWriteOnce",
            "modelCachePath": cache,
            "pvcSize": default_pvc_size(config),
            "notes": (
                "k3s ships StorageClass local-path. Do not apply a custom "
                "StorageClass unless the overlay requires it. PVC is RWO for one replica."
            ),
        },
    }
    secret_template = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "vllm-secrets", "namespace": namespace, "labels": labels},
        "type": "Opaque",
        "stringData": {
            "HF_TOKEN": "",
            "VLLM_API_KEY": "",
        },
    }
    pvc = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": "vllm-model-cache", "namespace": namespace, "labels": labels},
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "storageClassName": config.env.k8s_storage_class,
            "resources": {"requests": {"storage": default_pvc_size(config)}},
        },
    }
    http_probe = _probe(config.serving.health_path, port)
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "vllm", "namespace": namespace, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "strategy": {"type": "Recreate"},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "terminationGracePeriodSeconds": 60,
                    "containers": [
                        {
                            "name": "vllm",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "args": args,
                            "ports": [{"name": "http", "containerPort": port}],
                            "env": [
                                {"name": "HF_HOME", "value": cache},
                                {
                                    "name": "HF_HUB_DISABLE_XET",
                                    "valueFrom": {
                                        "configMapKeyRef": {
                                            "name": "vllm-serving",
                                            "key": "HF_HUB_DISABLE_XET",
                                        }
                                    },
                                },
                                {
                                    "name": "HF_TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "vllm-secrets",
                                            "key": "HF_TOKEN",
                                            "optional": True,
                                        }
                                    },
                                },
                                {
                                    "name": "VLLM_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "vllm-secrets",
                                            "key": "VLLM_API_KEY",
                                            "optional": True,
                                        }
                                    },
                                },
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": config.env.k8s_cpu_request,
                                    "memory": config.env.k8s_memory_request,
                                    "nvidia.com/gpu": "1",
                                },
                                "limits": {"nvidia.com/gpu": "1"},
                            },
                            "startupProbe": {
                                **http_probe,
                                "periodSeconds": 10,
                                "failureThreshold": 90,
                            },
                            "readinessProbe": {
                                **http_probe,
                                "periodSeconds": 5,
                                "failureThreshold": 6,
                            },
                            "livenessProbe": {
                                **http_probe,
                                "periodSeconds": 20,
                                "failureThreshold": 3,
                            },
                            "volumeMounts": [
                                {"name": "model-cache", "mountPath": cache},
                                {"name": "shm", "mountPath": "/dev/shm"},
                            ],
                        }
                    ],
                    "volumes": [
                        {
                            "name": "model-cache",
                            "persistentVolumeClaim": {"claimName": "vllm-model-cache"},
                        },
                        {
                            "name": "shm",
                            "emptyDir": {"medium": "Memory", "sizeLimit": "8Gi"},
                        },
                    ],
                },
            },
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "vllm", "namespace": namespace, "labels": labels},
        "spec": {
            "type": "ClusterIP",
            "selector": labels,
            "ports": [{"name": "http", "port": port, "targetPort": port, "protocol": "TCP"}],
        },
    }
    kustomization = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "namespace": namespace,
        "resources": [
            "namespace.yaml",
            "configmap.yaml",
            "storage.yaml",
            "pvc.yaml",
            "deployment.yaml",
            "service.yaml",
        ],
    }
    return {
        "namespace.yaml": namespace_doc,
        "configmap.yaml": configmap,
        "storage.yaml": storage,
        "secret.yaml.example": secret_template,
        "pvc.yaml": pvc,
        "deployment.yaml": deployment,
        "service.yaml": service,
        "kustomization.yaml": kustomization,
    }


def dump_yaml(document: dict[str, Any]) -> str:
    return yaml.safe_dump(document, sort_keys=False, explicit_start=False)


def write_manifests(config: ResolvedConfig, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, document in render_manifests(config).items():
        path = dest / name
        path.write_text(dump_yaml(document), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Phase 3 Kubernetes manifests (offline)")
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help="Directory to write YAML. Default: infra/kubernetes/base",
    )
    parser.add_argument(
        "--allow-env-topology",
        action="store_true",
        help="Honor COMPUTE_PROFILE/MODEL_CONFIG/TP/backend env overrides (off by default)",
    )
    args = parser.parse_args(argv)
    load_local_env()
    if not args.allow_env_topology:
        for key in (
            "COMPUTE_PROFILE",
            "MODEL_CONFIG",
            "DISTRIBUTED_EXECUTOR_BACKEND",
            "VLLM_TENSOR_PARALLEL_SIZE",
            "VLLM_PIPELINE_PARALLEL_SIZE",
            "VLLM_MODEL",
            "SERVED_MODEL_NAME",
            "MODEL_REVISION",
        ):
            os.environ.pop(key, None)
    profile_id = args.profile or default_profile_id()
    config = load_profile(profile_id)
    dest = Path(args.out) if args.out else repo_root() / "infra" / "kubernetes" / "base"
    try:
        paths = write_manifests(config, dest)
    except RenderError as exc:
        print(f"render failed: {exc}")
        return 1
    print(f"profile={profile_id}")
    print(f"out={dest}")
    for path in paths:
        print(f"wrote {path.name}")
    print("Do not apply these manifests until a GPU VM and k3s cluster exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
