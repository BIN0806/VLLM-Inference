"""SSH host-key install requires fingerprint comparison and detects mismatches."""

from __future__ import annotations

import base64
import os
import struct
from pathlib import Path

import pytest

from inference_platform.ssh_trust import HostKeyError, install_host_keys, parse_keyscan


def _ed25519_line(marker: str, material: bytes | None = None) -> str:
    algo = b"ssh-ed25519"
    pub = material or os.urandom(32)
    blob = struct.pack(">I", len(algo)) + algo + struct.pack(">I", len(pub)) + pub
    return f"{marker} ssh-ed25519 {base64.b64encode(blob).decode('ascii')}"


@pytest.mark.unit
def test_refuses_install_without_fingerprint_or_confirm(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    line = _ed25519_line("[example.invalid]:2222")
    with pytest.raises(HostKeyError, match="Refusing to install"):
        install_host_keys(line + "\n", dest, confirm=False)


@pytest.mark.unit
def test_installs_after_expected_fingerprint(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    line = _ed25519_line("[example.invalid]:2222")
    key = parse_keyscan(line)[0]
    installed = install_host_keys(
        line + "\n", dest, expected_fingerprint=key.fingerprint, confirm=False
    )
    assert len(installed) == 1
    assert dest.read_text(encoding="utf-8").count("ssh-ed25519") == 1
    assert key.blob_b64 in dest.read_text(encoding="utf-8")
    assert key.fingerprint.startswith("SHA256:")
    assert "=" not in key.fingerprint
    again = install_host_keys(line + "\n", dest, expected_fingerprint=key.fingerprint)
    assert again == []


@pytest.mark.unit
def test_explicit_confirm_installs_without_expected_fingerprint(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    line = _ed25519_line("example.invalid")
    installed = install_host_keys(line + "\n", dest, confirm=True)
    assert len(installed) == 1
    assert dest.read_text(encoding="utf-8").count("ssh-ed25519") == 1


@pytest.mark.unit
def test_mismatch_existing_key_is_an_error(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    first = _ed25519_line("[example.invalid]:2222", b"a" * 32)
    second = _ed25519_line("[example.invalid]:2222", b"b" * 32)
    first_fp = parse_keyscan(first)[0].fingerprint
    second_fp = parse_keyscan(second)[0].fingerprint
    install_host_keys(first + "\n", dest, expected_fingerprint=first_fp)
    with pytest.raises(HostKeyError, match="mismatch"):
        install_host_keys(second + "\n", dest, expected_fingerprint=second_fp)


@pytest.mark.unit
def test_wrong_expected_fingerprint_is_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    line = _ed25519_line("example.invalid")
    with pytest.raises(HostKeyError, match="does not match"):
        install_host_keys(line + "\n", dest, expected_fingerprint="SHA256:not-the-key")


@pytest.mark.unit
def test_trusted_known_hosts_allows_matching_fingerprint(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    trusted = tmp_path / "trusted"
    line = _ed25519_line("[example.invalid]:2222")
    trusted.write_text(line + "\n", encoding="utf-8")
    installed = install_host_keys(line + "\n", dest, trusted_known_hosts=trusted, confirm=False)
    assert len(installed) == 1


@pytest.mark.unit
def test_trusted_known_hosts_rejects_unknown_fingerprint(tmp_path: Path) -> None:
    dest = tmp_path / "known_hosts"
    trusted = tmp_path / "trusted"
    trusted.write_text(_ed25519_line("[other.invalid]:22") + "\n", encoding="utf-8")
    with pytest.raises(HostKeyError, match="not present in the trusted"):
        install_host_keys(
            _ed25519_line("[example.invalid]:2222") + "\n",
            dest,
            trusted_known_hosts=trusted,
        )


@pytest.mark.unit
def test_scan_script_does_not_trust_keyscan_output() -> None:
    from inference_platform.paths import repo_root

    script = (repo_root() / "scripts" / "ssh_scan_host.sh").read_text(encoding="utf-8")
    assert ">>" not in script
    assert "EXPECTED_FINGERPRINT" in script
    assert "CONFIRM" in script
    assert "TRUSTED_KNOWN_HOSTS" in script
    assert "mktemp" in script
    assert ".ssh/known_hosts" in script
