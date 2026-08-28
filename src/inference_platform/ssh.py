"""SSH command construction. Never reads private-key contents. Never disables host-key checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_HOST_KEY_MODES = frozenset({"no", "off", "false", "0", "disabled"})


class SSHConfigError(ValueError):
    """Raised when SSH configuration would be unsafe or incomplete."""


@dataclass(frozen=True)
class SSHTarget:
    host: str
    port: int
    user: str
    known_hosts: Path | None = None
    identity_file: Path | None = None
    connect_timeout: int = 15
    strict_host_key_checking: str = "yes"

    def __post_init__(self) -> None:
        mode = self.strict_host_key_checking.lower()
        if mode in FORBIDDEN_HOST_KEY_MODES:
            raise SSHConfigError(
                "SSH host-key checking cannot be disabled. "
                "Use a known_hosts file and `make ssh-scan-host` for first contact."
            )
        if mode not in {"yes", "accept-new"}:
            raise SSHConfigError(
                f"Unsupported StrictHostKeyChecking value {self.strict_host_key_checking!r}"
            )
        if not self.host or not self.host.strip():
            raise SSHConfigError("GPU_SSH_HOST is required for remote operations")
        if not (1 <= self.port <= 65535):
            raise SSHConfigError(f"Invalid SSH port: {self.port}")
        if self.identity_file is not None:
            object.__setattr__(self, "identity_file", Path(self.identity_file).expanduser())
            if self.identity_file.exists() and self.identity_file.stat().st_size == 0:
                raise SSHConfigError("GPU_SSH_IDENTITY_FILE points at an empty path")


def ssh_argv(target: SSHTarget, remote_command: str) -> list[str]:
    """Build an ssh argv list. The private key is never opened or logged."""

    cmd = [
        "ssh",
        "-p",
        str(target.port),
        "-l",
        target.user,
        "-o",
        "BatchMode=yes",
        "-o",
        f"StrictHostKeyChecking={target.strict_host_key_checking}",
        "-o",
        f"ConnectTimeout={target.connect_timeout}",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "PreferredAuthentications=publickey",
    ]
    if target.known_hosts is not None:
        cmd.extend(["-o", f"UserKnownHostsFile={target.known_hosts}"])
    if target.identity_file is not None:
        cmd.extend(
            [
                "-i",
                str(target.identity_file),
                "-o",
                "IdentitiesOnly=yes",
            ]
        )
    cmd.extend([target.host, "--", remote_command])
    return cmd


def ssh_keyscan_argv(host: str, port: int) -> list[str]:
    return ["ssh-keyscan", "-p", str(port), "-T", "10", host]


def tunnel_argv(
    target: SSHTarget, local_port: int, remote_host: str, remote_port: int
) -> list[str]:
    return ssh_argv(target, "sleep infinity")[:-2] + [
        "-N",
        "-L",
        f"{local_port}:{remote_host}:{remote_port}",
        target.host,
    ]
