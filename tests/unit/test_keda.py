"""Offline KEDA ScaledObject contract for Phase 4B."""

from __future__ import annotations

import pytest
import yaml

from inference_platform.paths import repo_root


@pytest.mark.unit
def test_scaledobject_targets_statefulset_with_waiting_value_metric() -> None:
    path = repo_root() / "infra" / "keda" / "scaledobject-vllm.yaml"
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    assert len(docs) == 1
    obj = docs[0]
    assert obj["apiVersion"] == "keda.sh/v1alpha1"
    assert obj["kind"] == "ScaledObject"
    spec = obj["spec"]
    ref = spec["scaleTargetRef"]
    assert ref["apiVersion"] == "apps/v1"
    assert ref["kind"] == "StatefulSet"
    assert ref["name"] == "vllm"
    assert spec["minReplicaCount"] == 1
    assert spec["maxReplicaCount"] == 2
    scale_down = spec["advanced"]["horizontalPodAutoscalerConfig"]["behavior"]["scaleDown"]
    assert scale_down["stabilizationWindowSeconds"] >= 60
    triggers = spec["triggers"]
    assert len(triggers) == 1
    trigger = triggers[0]
    assert trigger["type"] == "prometheus"
    assert trigger["metricType"] == "Value"
    meta = trigger["metadata"]
    assert meta["query"] == "sum(vllm:num_requests_waiting)"
    assert meta["ignoreNullValues"] == "false"
    assert "activationThreshold" not in meta
    raw = path.read_text(encoding="utf-8")
    assert "HTTPScaledObject" not in raw
    assert "minReplicaCount: 0" not in raw
