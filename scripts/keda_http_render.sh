#!/usr/bin/env bash
# Render kedacore/keda-add-ons-http 0.15.0 with the lab values. Does not install.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CHART_VERSION="0.15.0"
VALUES="$ROOT/infra/keda/http-add-on-values.yaml"
OUT="${1:-$ROOT/artifacts/keda-http-addon-${CHART_VERSION}.yaml}"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required to render the HTTP add-on chart." >&2
  exit 2
fi

helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
helm repo update kedacore >/dev/null
mkdir -p "$(dirname "$OUT")"
helm template http-add-on kedacore/keda-add-ons-http \
  --version "$CHART_VERSION" \
  --namespace keda \
  --values "$VALUES" \
  >"$OUT"

uv run python - "$OUT" "$VALUES" <<'PY'
import sys
from pathlib import Path

import yaml

rendered = Path(sys.argv[1]).read_text(encoding="utf-8")
values = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))
docs = [d for d in yaml.safe_load_all(rendered) if d]
kinds = {}
for doc in docs:
    kinds[doc.get("kind")] = kinds.get(doc.get("kind"), 0) + 1
assert values["images"]["tag"] == "0.15.0"
assert values["operator"]["watchNamespace"] == "inference"
assert values["interceptor"]["replicas"]["min"] == 1
assert values["interceptor"]["replicas"]["max"] == 1
assert values["scaler"]["replicas"] == 1
assert "0.15.0" in rendered
assert "HTTPScaledObject" in rendered  # chart still ships the deprecated CRD
assert not any(d.get("kind") == "HTTPScaledObject" for d in docs)
sts_targets = [
    d
    for d in docs
    if d.get("kind") == "ScaledObject"
    and d.get("spec", {}).get("scaleTargetRef", {}).get("kind") == "StatefulSet"
]
assert sts_targets == [], sts_targets
print(f"rendered {len(docs)} objects; kinds={sorted(kinds)}")
print(f"wrote {sys.argv[1]}")
PY
