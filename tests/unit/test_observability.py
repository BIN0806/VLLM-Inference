"""Offline Prometheus values and PromQL contract tests."""

from __future__ import annotations

import pytest
import yaml

from inference_platform.observability.prometheus import PrometheusQueryError, instant_query
from inference_platform.observability.promql import (
    REQUIRED_SERIES,
    acceptance_queries,
    load_promql_contract,
    required_series,
)
from inference_platform.paths import repo_root


@pytest.mark.unit
def test_promql_contract_covers_required_series() -> None:
    series = required_series()
    for name in REQUIRED_SERIES:
        assert name in series
    queries = acceptance_queries()
    blob = "\n".join(queries.values())
    assert "vllm:num_requests_running" in blob
    assert "vllm:num_requests_waiting" in blob
    assert "vllm:kv_cache_usage_perc" in blob
    assert "vllm:prompt_tokens_total" in blob
    assert "vllm:generation_tokens_total" in blob
    assert "vllm:time_to_first_token_seconds_bucket" in blob
    assert "vllm:e2e_request_latency_seconds_bucket" in blob
    assert "histogram_quantile" in blob
    contract = load_promql_contract()
    assert "queries" in contract
    raw = (repo_root() / "infra" / "observability" / "promql" / "vllm-acceptance.yaml").read_text(
        encoding="utf-8"
    )
    assert "_count" in raw and "sparse" in raw.lower()


@pytest.mark.unit
def test_kube_prometheus_stack_values_are_trimmed() -> None:
    path = repo_root() / "infra" / "observability" / "kube-prometheus-stack-values.yaml"
    values = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert values["grafana"]["enabled"] is False
    assert values["alertmanager"]["enabled"] is False
    assert values["defaultRules"]["create"] is False
    assert values["kubeApiServer"]["enabled"] is False
    assert values["kubeEtcd"]["enabled"] is False
    assert values["kubeControllerManager"]["enabled"] is False
    assert values["kubeScheduler"]["enabled"] is False
    assert values["kubeProxy"]["enabled"] is False
    assert values["kubeStateMetrics"]["enabled"] is False
    assert values["nodeExporter"]["enabled"] is False
    spec = values["prometheus"]["prometheusSpec"]
    assert spec["retention"] == "6h"
    assert spec["resources"]["limits"]["memory"] == "2Gi"
    assert spec["serviceMonitorSelectorNilUsesHelmValues"] is False
    storage = spec["storageSpec"]["volumeClaimTemplate"]["spec"]
    assert storage["storageClassName"] == "local-path"
    assert values["prometheus"]["ingress"]["enabled"] is False
    assert values["windowsMonitoring"]["enabled"] is False
    assert values["thanosRuler"]["enabled"] is False
    assert "keda" not in yaml.safe_dump(values).lower()
    assert "NodePort" not in yaml.safe_dump(values)


@pytest.mark.unit
def test_prometheus_query_refuses_non_loopback() -> None:
    with pytest.raises(PrometheusQueryError, match="loopback"):
        instant_query("http://10.0.0.8:9090", "up")
