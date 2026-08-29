"""Offline KEDA ScaledObject and HTTP Add-on contract for Phase 4B/4C."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from inference_platform.paths import repo_root


def _keda_dir() -> Path:
    return repo_root() / "infra" / "keda"


def _load(name: str) -> dict:
    path = _keda_dir() / name
    docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    assert len(docs) == 1, name
    return docs[0]


def _kinds_in_keda_dir() -> list[str]:
    kinds: list[str] = []
    for path in sorted(_keda_dir().glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if doc and "kind" in doc:
                kinds.append(str(doc["kind"]))
    return kinds


@pytest.mark.unit
def test_historical_prometheus_scaledobject_is_preserved() -> None:
    obj = _load("scaledobject-vllm-prometheus.yaml")
    assert obj["apiVersion"] == "keda.sh/v1alpha1"
    assert obj["kind"] == "ScaledObject"
    spec = obj["spec"]
    ref = spec["scaleTargetRef"]
    assert ref["apiVersion"] == "apps/v1"
    assert ref["kind"] == "StatefulSet"
    assert ref["name"] == "vllm"
    assert spec["minReplicaCount"] == 1
    assert spec["maxReplicaCount"] == 2
    trigger = spec["triggers"][0]
    assert trigger["type"] == "prometheus"
    assert trigger["metricType"] == "Value"
    assert trigger["metadata"]["query"] == "sum(vllm:num_requests_waiting)"
    assert trigger["metadata"]["ignoreNullValues"] == "false"
    raw = (_keda_dir() / "scaledobject-vllm-prometheus.yaml").read_text(encoding="utf-8")
    assert "historical" in raw.lower()
    assert "Do not apply this while" in raw


@pytest.mark.unit
def test_live_http_scaledobject_targets_statefulset_from_zero() -> None:
    obj = _load("scaledobject-vllm.yaml")
    assert obj["apiVersion"] == "keda.sh/v1alpha1"
    assert obj["kind"] == "ScaledObject"
    spec = obj["spec"]
    ref = spec["scaleTargetRef"]
    assert ref["apiVersion"] == "apps/v1"
    assert ref["kind"] == "StatefulSet"
    assert ref["name"] == "vllm"
    assert spec["minReplicaCount"] == 0
    assert spec["maxReplicaCount"] == 2
    assert spec["cooldownPeriod"] == 300
    assert spec["pollingInterval"] == 15
    trigger = spec["triggers"][0]
    assert trigger["type"] == "external-push"
    meta = trigger["metadata"]
    assert meta["scalerAddress"] == "keda-add-ons-http-external-scaler.keda:9090"
    assert meta["interceptorRoute"] == "vllm"
    raw = (_keda_dir() / "scaledobject-vllm.yaml").read_text(encoding="utf-8")
    assert "HTTPScaledObject" not in raw or "Do not create kind: HTTPScaledObject" in raw


@pytest.mark.unit
def test_interceptorroute_v1beta1_holds_for_cold_start() -> None:
    obj = _load("interceptorroute-vllm.yaml")
    assert obj["apiVersion"] == "http.keda.sh/v1beta1"
    assert obj["kind"] == "InterceptorRoute"
    assert obj["metadata"]["name"] == "vllm"
    spec = obj["spec"]
    assert spec["target"]["service"] == "vllm"
    assert spec["target"]["port"] == 8000
    assert spec["scalingMetric"]["concurrency"]["targetValue"] == 1
    timeouts = spec["timeouts"]
    assert timeouts["readiness"] == "240s"
    assert timeouts["request"] == "420s"
    assert timeouts["responseHeader"] == "300s"
    hosts = spec["rules"][0]["hosts"]
    assert "*" in hosts
    assert "coldStart" not in spec
    assert obj["kind"] != "HTTPScaledObject"


@pytest.mark.unit
def test_http_addon_values_are_constrained_and_pinned() -> None:
    values = yaml.safe_load((_keda_dir() / "http-add-on-values.yaml").read_text(encoding="utf-8"))
    assert values["images"]["tag"] == "0.15.0"
    assert "latest" not in values["images"]["tag"]
    assert values["operator"]["watchNamespace"] == "inference"
    assert values["interceptor"]["replicas"]["min"] == 1
    assert values["interceptor"]["replicas"]["max"] == 1
    assert values["scaler"]["replicas"] == 1
    assert values["scaler"]["metrics"]["prometheus"]["port"] == 2223
    assert values["interceptor"]["tls"]["enabled"] is False
    assert values["interceptor"]["readinessTimeout"] == "240s"
    assert values["interceptor"]["requestTimeout"] == "420s"
    assert values["interceptor"]["responseHeaderTimeout"] == "300s"
    for component in ("operator", "scaler", "interceptor"):
        memory = values[component]["resources"]["limits"]["memory"]
        assert memory.endswith("Mi")
        assert int(memory.removesuffix("Mi")) <= 128


@pytest.mark.unit
def test_application_manifests_do_not_create_httpscaledobject() -> None:
    assert "HTTPScaledObject" not in _kinds_in_keda_dir()


@pytest.mark.unit
def test_live_and_historical_scaledobjects_share_name_but_not_both_apply() -> None:
    live = _load("scaledobject-vllm.yaml")
    historical = _load("scaledobject-vllm-prometheus.yaml")
    assert live["metadata"]["name"] == historical["metadata"]["name"] == "vllm"
    assert live["spec"]["triggers"][0]["type"] != historical["spec"]["triggers"][0]["type"]
    live_triggers = {t["type"] for t in live["spec"]["triggers"]}
    hist_triggers = {t["type"] for t in historical["spec"]["triggers"]}
    assert live_triggers == {"external-push"}
    assert hist_triggers == {"prometheus"}


@pytest.mark.unit
def test_http_addon_servicemonitor_scrapes_scaler_2223() -> None:
    obj = _load("servicemonitor-http-addon.yaml")
    assert obj["kind"] == "ServiceMonitor"
    assert obj["metadata"]["namespace"] == "keda"
    endpoint = obj["spec"]["endpoints"][0]
    assert endpoint["port"] == "metrics"
    assert obj["spec"]["selector"]["matchLabels"]["app.kubernetes.io/component"] == "scaler"
