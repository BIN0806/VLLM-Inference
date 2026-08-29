#!/usr/bin/env python3
"""One-shot OpenAI-compatible SSE request. Does not retry.

Used for Phase 4C warm and cold-start checks through the HTTP interceptor.
Client timeout must exceed the interceptor request budget (420s).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="qwen2.5-1.5b-instruct-awq")
    parser.add_argument("--timeout", type=float, default=480.0)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--prompt", default="Say hello in one short sentence.")
    args = parser.parse_args()

    body = json.dumps(
        {
            "model": args.model,
            "stream": True,
            "max_tokens": args.max_tokens,
            "messages": [{"role": "user", "content": args.prompt}],
        }
    ).encode("utf-8")
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    arrival = time.time()
    print(f"arrival_unix={arrival:.3f}", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as resp:
            status = resp.status
            headers = {k.lower(): v for k, v in resp.headers.items()}
            cold = headers.get("x-keda-http-cold-start", "")
            print(f"http_status={status}", flush=True)
            print(f"x_keda_http_cold_start={cold!r}", flush=True)
            first_token: float | None = None
            chunks: list[str] = []
            saw_done = False
            content = []
            while True:
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        saw_done = True
                        break
                    chunks.append(payload)
                    if first_token is None:
                        first_token = time.time()
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        content.append(delta)
            done = time.time()
            text = "".join(content)
            print(f"first_token_unix={first_token if first_token else ''}", flush=True)
            print(f"completion_unix={done:.3f}", flush=True)
            print(f"hold_s={done - arrival:.3f}", flush=True)
            if first_token is not None:
                print(f"ttft_s={first_token - arrival:.3f}", flush=True)
            print(f"sse_chunks={len(chunks)}", flush=True)
            print(f"saw_done={str(saw_done).lower()}", flush=True)
            print(f"output_chars={len(text)}", flush=True)
            ok = (
                status == 200
                and saw_done
                and len(chunks) > 0
                and len(text) > 0
                and status not in {502, 504}
            )
            print(f"accepted={str(ok).lower()}", flush=True)
            return 0 if ok else 1
    except urllib.error.HTTPError as exc:
        print(f"http_status={exc.code}", flush=True)
        print(f"error={exc}", flush=True)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"error={type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
