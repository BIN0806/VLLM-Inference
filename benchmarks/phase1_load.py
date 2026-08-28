#!/usr/bin/env python3
"""Phase 1 load benchmark. Reads the workload contract; does not embed lengths in code."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from inference_client.client import build_client, stream_chat_completion
from inference_client.health import get_json
from inference_platform.config import load_local_env, load_profile
from inference_platform.paths import artifacts_dir
from inference_platform.secrets import redact_mapping


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * q
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def apply_scenario(config, scenario: str | None):
    if not scenario:
        return config.workload
    extra = config.workload.optional_scenarios.get(scenario)
    if extra is None:
        raise SystemExit(f"Unknown workload scenario {scenario!r}")
    return config.workload.model_copy(update=extra)


def scrape_metrics(base_url: str, api_key: str | None, tls_verify: bool) -> str | None:
    try:
        status, body = get_json(base_url, "/metrics", api_key=api_key, tls_verify=tls_verify)
    except Exception:  # noqa: BLE001
        return None
    if status != 200 or not isinstance(body, str):
        return None
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 benchmark (contract-driven)")
    parser.add_argument("--profile", default="vast-single-gpu")
    parser.add_argument("--scenario", default=None, help="optional medium|long override")
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--warmup", type=int, default=None)
    args = parser.parse_args()
    load_local_env()
    config = load_profile(args.profile)
    workload = apply_scenario(config, args.scenario)
    concurrency = args.concurrency or workload.concurrency_levels[0]
    duration = args.duration or workload.measurement_duration_seconds
    warmup = args.warmup or workload.warmup_duration_seconds
    env = config.env
    client = build_client(
        env.vllm_base_url,
        env.vllm_api_key,
        timeout=workload.request_timeout_seconds,
        tls_verify=env.vllm_tls_verify,
    )
    template = workload.prompt_template or "Write about {topic}."
    topics = workload.topics or ["inference"]

    def one(i: int):
        prompt = template.format(topic=topics[i % len(topics)])
        return stream_chat_completion(
            client,
            model=config.served_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=workload.requested_output_tokens,
            timeout=workload.request_timeout_seconds,
        )

    def run_window(seconds: int, label: str) -> list[dict]:
        deadline = time.monotonic() + seconds
        rows: list[dict] = []
        index = 0
        while time.monotonic() < deadline:
            batch = min(concurrency, 32)
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futs = [pool.submit(one, index + j) for j in range(batch)]
                index += batch
                for fut in as_completed(futs):
                    item = fut.result()
                    rows.append(
                        {
                            "window": label,
                            "status": item.status,
                            "ttft_ms": item.ttft_ms,
                            "e2e_ms": item.e2e_ms,
                            "output_chars": len(item.output_text),
                            "terminal": item.terminal,
                            "error": item.error,
                            "usage": item.usage,
                        }
                    )
        return rows

    metrics_before = scrape_metrics(env.vllm_base_url, env.vllm_api_key, env.vllm_tls_verify)
    warmup_rows = run_window(warmup, "warmup")
    t0 = time.monotonic()
    measure_rows = run_window(duration, "steady")
    elapsed = max(time.monotonic() - t0, 1e-6)
    metrics_after = scrape_metrics(env.vllm_base_url, env.vllm_api_key, env.vllm_tls_verify)

    attempted = len(measure_rows)
    ok = [row for row in measure_rows if row["status"] == "ok"]
    errors = attempted - len(ok)
    in_tokens = 0
    out_tokens = 0
    for row in ok:
        usage = row.get("usage") or {}
        in_tokens += int(usage.get("prompt_tokens") or 0)
        out_tokens += int(usage.get("completion_tokens") or 0)
    ttfts = [row["ttft_ms"] for row in ok if row["ttft_ms"] is not None]
    e2e = [row["e2e_ms"] for row in ok if row["e2e_ms"] is not None]
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": config.profile.id,
        "scenario": args.scenario or workload.id,
        "classification": workload.classification,
        "hardware_note": "Record GPU/model/engine from discovery; this file is client-side.",
        "config": config.public_dict(),
        "concurrency": concurrency,
        "warmup_seconds": warmup,
        "measurement_seconds": duration,
        "attempted_requests": attempted,
        "successful_requests": len(ok),
        "error_count": errors,
        "error_rate": errors / attempted if attempted else None,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "input_tokens_per_sec": in_tokens / elapsed,
        "output_tokens_per_sec": out_tokens / elapsed,
        "requests_per_sec": len(ok) / elapsed,
        "ttft_ms": {
            "p50": percentile(ttfts, 0.50),
            "p95": percentile(ttfts, 0.95),
            "p99": percentile(ttfts, 0.99),
        },
        "e2e_ms": {
            "p50": percentile(e2e, 0.50),
            "p95": percentile(e2e, 0.95),
            "mean": statistics.fmean(e2e) if e2e else None,
        },
        "aspirational_5000_output_tok_s": False,
        "failed_requests_included_in_denominator": True,
        "metrics_before_present": metrics_before is not None,
        "metrics_after_present": metrics_after is not None,
        "warmup_requests": len(warmup_rows),
    }
    out_dir = artifacts_dir() / "phase1"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "benchmark_summary.json").write_text(
        json.dumps(redact_mapping(summary), indent=2) + "\n"
    )
    (out_dir / "benchmark_raw.jsonl").write_text(
        "".join(json.dumps(redact_mapping(row)) + "\n" for row in warmup_rows + measure_rows)
    )
    print(json.dumps(redact_mapping(summary), indent=2))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
