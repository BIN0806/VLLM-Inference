"""SSH abstraction safety tests."""

from __future__ import annotations

import pytest

from inference_platform.config import load_profile
from inference_platform.paths import default_known_hosts_path
from inference_platform.ssh import SSHConfigError, SSHTarget, ssh_argv, tunnel_argv


@pytest.mark.unit
def test_refuses_disabled_host_key_checking() -> None:
    with pytest.raises(SSHConfigError, match="cannot be disabled"):
        SSHTarget(host="example.invalid", port=22, user="root", strict_host_key_checking="no")


@pytest.mark.unit
def test_argv_uses_agent_and_batch_mode() -> None:
    target = SSHTarget(host="example.invalid", port=2222, user="ubuntu")
    argv = ssh_argv(target, "nvidia-smi")
    assert argv[:3] == ["ssh", "-p", "2222"]
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert "PasswordAuthentication=no" in argv
    assert argv[-3:] == ["example.invalid", "--", "nvidia-smi"]
    joined = " ".join(argv)
    assert "BEGIN" not in joined
    assert "PRIVATE KEY" not in joined


@pytest.mark.unit
def test_identity_file_is_path_only(tmp_path) -> None:
    key_path = tmp_path / "id_ed25519"
    key_path.write_text("dummy-not-read-by-constructor\n")
    target = SSHTarget(host="example.invalid", port=22, user="root", identity_file=key_path)
    argv = ssh_argv(target, "true")
    assert str(key_path) in argv
    # Constructor must not need the key contents; the file is not re-read here.


@pytest.mark.unit
def test_tunnel_does_not_embed_api_key() -> None:
    target = SSHTarget(host="example.invalid", port=10173, user="root")
    argv = tunnel_argv(target, 8000, "127.0.0.1", 18000)
    assert "-L" in argv
    assert "8000:127.0.0.1:18000" in argv
    assert all("VLLM_API_KEY" not in part for part in argv)


@pytest.mark.unit
def test_resolved_ssh_target_uses_project_known_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPU_SSH_HOST", "example.invalid")
    monkeypatch.setenv("GPU_SSH_PORT", "2222")
    monkeypatch.delenv("GPU_SSH_KNOWN_HOSTS", raising=False)
    target = load_profile("authoring").ssh_target()
    assert target.known_hosts == default_known_hosts_path()
    argv = ssh_argv(target, "true")
    assert f"UserKnownHostsFile={default_known_hosts_path()}" in " ".join(argv)
