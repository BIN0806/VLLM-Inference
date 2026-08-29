"""Render provider-neutral Kubernetes manifests from a composed profile.

Does not talk to a cluster. Does not install k3s, the NVIDIA toolkit, the
device plugin, Prometheus, or KEDA. Fail closed if the selected compute
topology is not a complete mp replica (TP=1, PP=1).
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

K8S_REPLICA_COMPUTE = frozenset({"k8s-replica", "k8s-replicas"})


class RenderError(ValueError):
    """Raised when the selected profile cannot be rendered as a vLLM replica."""


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
    if compute is None or compute.id not in {*K8S_REPLICA_COMPUTE, "k8s-replica-zero"}:
        raise RenderError("Kubernetes render requires compute profile k8s-replica or k8s-replicas")
    if compute.id == "k8s-replica-zero":
        raise RenderError("k8s-replica-zero is a later gate; render the warm replica only")
    report = validate_topology(config, None)
    fails = [issue for issue in report.issues if issue.severity == "FAIL"]
    if fails:
        raise RenderError(fails[0].message)
    if config.tensor_parallel_size != 1 or config.pipeline_parallel_size != 1:
        raise RenderError("Replica render requires TP=1 and PP=1")
    if config.distributed_executor_backend != "mp":
        raise RenderError("Replica render refuses Ray; use mp")
    if config.env.allow_model_fallback:
        raise RenderError("Refusing to render while ALLOW_MODEL_FALLBACK is enabled")
    if config.env.allow_tp_fallback:
        raise RenderError("Refusing to render while ALLOW_TP_FALLBACK is enabled")


def uses_statefulset(config: ResolvedConfig) -> bool:
    if config.k8s_kind() == "StatefulSet":
        return True
    return bool(config.compute and config.compute.id == "k8s-replicas")


def default_render_dir(profile_id: str) -> Path:
    root = repo_root() / "infra" / "kubernetes"
    if profile_id == "vast-k3s-replicas":
        return root / "overlays" / "vast-k3s-replicas"
    return root / "base"


def _labels() -> dict[str, str]:
    return {"app": "inference-platform", "component": "vllm"}


def _container(config: ResolvedConfig, *, metrics_port: bool) -> dict[str, Any]:
    port = config.serving.container_port
    cache = config.model_cache_path()
    image = config.vllm_image_ref()
    http_probe = _probe(config.serving.health_path, port)
    requests: dict[str, str] = {
        "cpu": config.k8s_cpu_request_value(),
        "memory": config.k8s_memory_request_value(),
        "nvidia.com/gpu": "1",
    }
    limits: dict[str, str] = {"nvidia.com/gpu": "1"}
    cpu_limit = config.k8s_cpu_limit_value()
    memory_limit = config.k8s_memory_limit_value()
    if cpu_limit:
        limits["cpu"] = cpu_limit
    if memory_limit:
        limits["memory"] = memory_limit
    ports = [{"name": "http", "containerPort": port}]
    if metrics_port:
        ports.append({"name": "metrics", "containerPort": port})
    return {
        "name": "vllm",
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "args": vllm_args(config),
        "ports": ports,
        "env": [
            {"name": "HF_HOME", "value": cache},
            {
                "name": "HF_HUB_DISABLE_XET",
                "valueFrom": {
                    "configMapKeyRef": {"name": "vllm-serving", "key": "HF_HUB_DISABLE_XET"}
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
        "resources": {"requests": requests, "limits": limits},
        "startupProbe": {**http_probe, "periodSeconds": 10, "failureThreshold": 90},
        "readinessProbe": {**http_probe, "periodSeconds": 5, "failureThreshold": 6},
        "livenessProbe": {**http_probe, "periodSeconds": 20, "failureThreshold": 3},
        "volumeMounts": [
            {"name": "model-cache", "mountPath": cache},
            {"name": "shm", "mountPath": "/dev/shm"},
        ],
    }


def _pod_spec(config: ResolvedConfig, *, claim_via_template: bool) -> dict[str, Any]:
    shm = {
        "name": "shm",
        "emptyDir": {"medium": "Memory", "sizeLimit": config.k8s_shm_size_value()},
    }
    volumes: list[dict[str, Any]] = [shm]
    if not claim_via_template:
        volumes.insert(
            0,
            {
                "name": "model-cache",
                "persistentVolumeClaim": {"claimName": "vllm-model-cache"},
            },
        )
    return {
        "terminationGracePeriodSeconds": 60,
        "enableServiceLinks": False,
        "containers": [_container(config, metrics_port=claim_via_template)],
        "volumes": volumes,
    }


def _shared_docs(config: ResolvedConfig) -> dict[str, dict[str, Any]]:
    namespace = config.env.k8s_namespace
    port = config.serving.container_port
    cache = config.model_cache_path()
    image = config.vllm_image_ref()
    plugin = config.pins.get("charts_and_operators", {}).get("nvidia_device_plugin", "0.20.0")
    labels = _labels()
    stateful = uses_statefulset(config)
    storage_notes = (
        "StatefulSet volumeClaimTemplates create one local-path RWO PVC per replica. "
        "Each replica has its own Hugging Face cache. Those volumes persist across "
        "pod restarts on this VM. They do not survive destruction of the Vast VM "
        "and are not provider-persistent storage. Do not share a writable cache."
        if stateful
        else (
            "k3s local-path PVC persists across pod restarts on this VM. "
            "It does not survive destruction of the Vast VM and is not "
            "provider-persistent storage. RWO for one replica."
        )
    )
    return {
        "namespace.yaml": {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace, "labels": {"app": "inference-platform"}},
        },
        "configmap.yaml": {
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
                "WORKLOAD_KIND": config.k8s_kind() if stateful else "Deployment",
                "REPLICAS": str(config.k8s_replicas()),
                "HF_HUB_DISABLE_XET": "1" if config.env.hf_hub_disable_xet else "0",
            },
        },
        "storage.yaml": {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "vllm-storage", "namespace": namespace, "labels": labels},
            "data": {
                "storageClassName": config.env.k8s_storage_class,
                "accessMode": "ReadWriteOnce",
                "modelCachePath": cache,
                "pvcSize": default_pvc_size(config),
                "perReplica": "true" if stateful else "false",
                "notes": storage_notes,
            },
        },
        "secret.yaml.example": {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "vllm-secrets", "namespace": namespace, "labels": labels},
            "type": "Opaque",
            "stringData": {"HF_TOKEN": "", "VLLM_API_KEY": ""},
        },
        "service.yaml": {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "vllm", "namespace": namespace, "labels": labels},
            "spec": {
                "type": "ClusterIP",
                "selector": labels,
                "ports": [{"name": "http", "port": port, "targetPort": port, "protocol": "TCP"}],
            },
        },
    }


def _metrics_service(config: ResolvedConfig) -> dict[str, Any]:
    namespace = config.env.k8s_namespace
    port = config.serving.container_port
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": "vllm-metrics",
            "namespace": namespace,
            "labels": {"app": "inference-platform", "component": "vllm-metrics"},
        },
        "spec": {
            "type": "ClusterIP",
            "selector": _labels(),
            "ports": [
                {
                    "name": "metrics",
                    "port": port,
                    "targetPort": "metrics",
                    "protocol": "TCP",
                }
            ],
        },
    }


def _service_monitor(config: ResolvedConfig) -> dict[str, Any]:
    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "ServiceMonitor",
        "metadata": {
            "name": "vllm",
            "namespace": config.env.k8s_namespace,
            "labels": {"app": "inference-platform", "component": "vllm"},
        },
        "spec": {
            "selector": {"matchLabels": {"app": "inference-platform", "component": "vllm-metrics"}},
            "namespaceSelector": {"matchNames": [config.env.k8s_namespace]},
            "endpoints": [
                {
                    "port": "metrics",
                    "path": config.serving.metrics_path,
                    "interval": "15s",
                }
            ],
        },
    }


def _headless_service(config: ResolvedConfig) -> dict[str, Any]:
    namespace = config.env.k8s_namespace
    port = config.serving.container_port
    labels = _labels()
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": "vllm-headless",
            "namespace": namespace,
            "labels": {**labels, "service": "headless"},
        },
        "spec": {
            "type": "ClusterIP",
            "clusterIP": "None",
            "selector": labels,
            "ports": [{"name": "http", "port": port, "targetPort": port, "protocol": "TCP"}],
        },
    }


def render_manifests(config: ResolvedConfig) -> dict[str, dict[str, Any]]:
    """Return filename -> Kubernetes object. Secret is a template with empty values."""

    _validate_renderable(config)
    namespace = config.env.k8s_namespace
    labels = _labels()
    docs = _shared_docs(config)
    stateful = uses_statefulset(config)

    if stateful:
        replicas = config.k8s_replicas()
        docs["headless-service.yaml"] = _headless_service(config)
        docs["statefulset.yaml"] = {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {"name": "vllm", "namespace": namespace, "labels": labels},
            "spec": {
                "serviceName": "vllm-headless",
                "replicas": replicas,
                "podManagementPolicy": "OrderedReady",
                "selector": {"matchLabels": labels},
                "updateStrategy": {"type": "RollingUpdate"},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": _pod_spec(config, claim_via_template=True),
                },
                "volumeClaimTemplates": [
                    {
                        "metadata": {"name": "model-cache", "labels": labels},
                        "spec": {
                            "accessModes": ["ReadWriteOnce"],
                            "storageClassName": config.env.k8s_storage_class,
                            "resources": {"requests": {"storage": default_pvc_size(config)}},
                        },
                    }
                ],
            },
        }
        overlay = config.profile.k8s
        if overlay is None or overlay.metrics_service:
            docs["metrics-service.yaml"] = _metrics_service(config)
        if overlay is None or overlay.service_monitor:
            docs["servicemonitor.yaml"] = _service_monitor(config)
        resources = [
            "namespace.yaml",
            "configmap.yaml",
            "storage.yaml",
            "headless-service.yaml",
            "statefulset.yaml",
            "service.yaml",
        ]
        if "metrics-service.yaml" in docs:
            resources.append("metrics-service.yaml")
        docs["runtime-class-patch.yaml"] = {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {"name": "vllm"},
            "spec": {"template": {"spec": {"runtimeClassName": "nvidia"}}},
        }
        docs["kustomization.yaml"] = {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": namespace,
            "resources": resources,
            "patches": [
                {
                    "path": "runtime-class-patch.yaml",
                    "target": {
                        "group": "apps",
                        "version": "v1",
                        "kind": "StatefulSet",
                        "name": "vllm",
                    },
                }
            ],
        }
        if "servicemonitor.yaml" in docs:
            docs["kustomization-monitoring.yaml"] = {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "namespace": namespace,
                "resources": ["servicemonitor.yaml"],
            }
        return docs

    docs["pvc.yaml"] = {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": "vllm-model-cache", "namespace": namespace, "labels": labels},
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "storageClassName": config.env.k8s_storage_class,
            "resources": {"requests": {"storage": default_pvc_size(config)}},
        },
    }
    docs["deployment.yaml"] = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "vllm", "namespace": namespace, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "strategy": {"type": "Recreate"},
            "template": {
                "metadata": {"labels": labels},
                "spec": _pod_spec(config, claim_via_template=False),
            },
        },
    }
    docs["kustomization.yaml"] = {
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
    return docs


def dump_yaml(document: dict[str, Any]) -> str:
    return yaml.safe_dump(document, sort_keys=False, explicit_start=False)


def write_manifests(config: ResolvedConfig, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, document in render_manifests(config).items():
        path = dest / name
        path.write_text(dump_yaml(document), encoding="utf-8")
        written.append(path)
    if uses_statefulset(config):
        plugin_src = (
            repo_root()
            / "infra"
            / "kubernetes"
            / "overlays"
            / "vast-k3s"
            / "nvidia-device-plugin-k3s-patch.yaml"
        )
        if plugin_src.is_file():
            plugin_dest = dest / "nvidia-device-plugin-k3s-patch.yaml"
            plugin_dest.write_text(plugin_src.read_text(encoding="utf-8"), encoding="utf-8")
            written.append(plugin_dest)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Kubernetes manifests (offline)")
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help="Directory to write YAML. Default: Phase 3 base or Phase 4A overlay.",
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
            "K8S_PVC_SIZE",
            "K8S_CPU_REQUEST",
            "K8S_CPU_LIMIT",
            "K8S_MEMORY_REQUEST",
            "K8S_MEMORY_LIMIT",
            "K8S_SHM_SIZE",
            "VLLM_MAX_MODEL_LEN",
            "VLLM_MAX_NUM_SEQS",
            "VLLM_IMAGE",
        ):
            os.environ.pop(key, None)
    profile_id = args.profile or default_profile_id()
    config = load_profile(profile_id)
    dest = Path(args.out) if args.out else default_render_dir(profile_id)
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
