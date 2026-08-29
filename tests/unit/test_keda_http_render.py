"""Helm template contract for KEDA HTTP Add-on 0.15.0 when Helm is installed."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
import yaml

from inference_platform.paths import repo_root


@pytest.mark.unit
def test_helm_template_http_addon_0_15_0() -> None:
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")
    root = repo_root()
    out = root / "artifacts" / "keda-http-addon-0.15.0.yaml"
    env = os.environ.copy()
    proc = subprocess.run(
        [str(root / "scripts" / "keda_http_render.sh"), str(out)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    docs = [d for d in yaml.safe_load_all(out.read_text(encoding="utf-8")) if d]
    kinds = {d.get("kind") for d in docs}
    assert "CustomResourceDefinition" in kinds
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "ScaledObject" in kinds
    assert not any(d.get("kind") == "HTTPScaledObject" for d in docs)
    crd_names = [d["metadata"]["name"] for d in docs if d.get("kind") == "CustomResourceDefinition"]
    assert any(name.startswith("interceptorroutes.http.keda.sh") for name in crd_names)
    images = {
        c.get("image")
        for d in docs
        if d.get("kind") in {"Deployment", "StatefulSet"}
        for c in d.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    }
    assert any(image and image.endswith(":0.15.0") for image in images)
    rendered = out.read_text(encoding="utf-8")
    assert "KEDA_HTTP_OPERATOR_WATCH_NAMESPACE" in rendered
    assert "inference" in rendered
    interceptor_so = [
        d
        for d in docs
        if d.get("kind") == "ScaledObject"
        and d.get("spec", {}).get("scaleTargetRef", {}).get("kind") == "Deployment"
    ]
    assert interceptor_so
    assert interceptor_so[0]["spec"]["minReplicaCount"] == 1
    assert interceptor_so[0]["spec"]["maxReplicaCount"] == 1
    assert not any(d.get("spec", {}).get("scaleTargetRef", {}).get("name") == "vllm" for d in docs)
