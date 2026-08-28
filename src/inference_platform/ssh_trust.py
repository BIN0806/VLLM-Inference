"""First-contact SSH host-key install. Never treat ssh-keyscan as already trusted."""

from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from inference_platform.paths import default_known_hosts_path


class HostKeyError(ValueError):
    """Unsafe or conflicting host key."""


@dataclass(frozen=True)
class HostKey:
    marker: str
    key_type: str
    blob_b64: str
    comment: str = ""

    @property
    def line(self) -> str:
        extra = f" {self.comment}" if self.comment else ""
        return f"{self.marker} {self.key_type} {self.blob_b64}{extra}"

    @property
    def fingerprint(self) -> str:
        raw = base64.b64decode(self.blob_b64)
        digest = hashlib.sha256(raw).digest()
        return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def parse_keyscan(output: str) -> list[HostKey]:
    keys: list[HostKey] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        marker, key_type, blob = parts[0], parts[1], parts[2]
        comment = " ".join(parts[3:]) if len(parts) > 3 else ""
        keys.append(HostKey(marker=marker, key_type=key_type, blob_b64=blob, comment=comment))
    return keys


def parse_known_hosts(text: str) -> list[HostKey]:
    return parse_keyscan(text)


def existing_for(keys: list[HostKey], marker: str, key_type: str) -> list[HostKey]:
    return [item for item in keys if item.marker == marker and item.key_type == key_type]


def install_host_keys(
    candidate_text: str,
    known_hosts_path: Path,
    *,
    expected_fingerprint: str | None = None,
    confirm: bool = False,
) -> list[HostKey]:
    candidates = parse_keyscan(candidate_text)
    if not candidates:
        raise HostKeyError("ssh-keyscan produced no host keys")
    fingerprints = {item.fingerprint for item in candidates}
    if expected_fingerprint:
        expected = expected_fingerprint.strip()
        if expected not in fingerprints:
            raise HostKeyError(
                "Candidate fingerprint does not match EXPECTED_FINGERPRINT. "
                f"saw={sorted(fingerprints)} expected={expected}"
            )
    elif not confirm:
        raise HostKeyError(
            "Refusing to install unverified ssh-keyscan output. Compare the SHA256 "
            "fingerprint out of band, then re-run with EXPECTED_FINGERPRINT=SHA256:... "
            "or CONFIRM=yes."
        )

    known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_known_hosts(
        known_hosts_path.read_text(encoding="utf-8") if known_hosts_path.is_file() else ""
    )
    seen = {" ".join([item.marker, item.key_type, item.blob_b64]) for item in existing}
    installed: list[HostKey] = []
    new_lines: list[str] = []
    for key in candidates:
        matches = existing_for(existing, key.marker, key.key_type)
        for prior in matches:
            if prior.blob_b64 != key.blob_b64:
                raise HostKeyError(
                    f"Host key mismatch for {key.marker} ({key.key_type}): "
                    f"known {prior.fingerprint} vs candidate {key.fingerprint}"
                )
        compact = " ".join([key.marker, key.key_type, key.blob_b64])
        if compact in seen:
            continue
        seen.add(compact)
        new_lines.append(key.line)
        installed.append(key)
        existing.append(key)
    if new_lines:
        previous = (
            known_hosts_path.read_text(encoding="utf-8") if known_hosts_path.is_file() else ""
        )
        prefix = "\n" if previous and not previous.endswith("\n") else ""
        with known_hosts_path.open("a", encoding="utf-8") as handle:
            handle.write(prefix + "\n".join(new_lines) + "\n")
    return installed


def format_fingerprints(keys: list[HostKey]) -> str:
    return "\n".join(f"{item.marker} {item.key_type} {item.fingerprint}" for item in keys)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify and install ssh-keyscan output")
    parser.add_argument("action", choices=["show", "install"])
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--known-hosts", default=None)
    parser.add_argument("--expected-fingerprint", default=None)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    candidate = Path(args.candidate).read_text(encoding="utf-8")
    keys = parse_keyscan(candidate)
    print(format_fingerprints(keys) or "(no keys)")
    if args.action == "show":
        return 0 if keys else 1
    dest = Path(args.known_hosts) if args.known_hosts else default_known_hosts_path()
    try:
        installed = install_host_keys(
            candidate,
            dest,
            expected_fingerprint=args.expected_fingerprint,
            confirm=args.confirm,
        )
    except HostKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"installed {len(installed)} new key(s) into {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
