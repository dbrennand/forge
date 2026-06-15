from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from forge.config import HOST_SERVICES_SSH_AUTH_SOCK
from forge.env import collect_forwarded_env, resolve_image, resolve_ssh_auth_sock


def test_resolve_image_precedence() -> None:
    """Prefer CLI image overrides before env and default values."""
    assert resolve_image("cli:image", {"FORGE_IMAGE": "env:image"}) == "cli:image"
    assert resolve_image(None, {"FORGE_IMAGE": "env:image"}) == "env:image"
    assert resolve_image(None, {}) == "ghcr.io/dbrennand/forge:latest"


def test_collect_forwarded_env() -> None:
    """Forward only whitelisted environment variables with non-empty values."""
    forwarded = collect_forwarded_env(
        {
            "OPENAI_API_KEY": "openai",
            "GITHUB_TOKEN": "github",
            "GH_TOKEN": "",
            "SSH_AUTH_SOCK": "/tmp/agent.sock",
            "TERM": "xterm-256color",
            "LANG": "en_GB.UTF-8",
            "EXTRA": "ignored",
        }
    )

    assert forwarded == {
        "OPENAI_API_KEY": "openai",
        "GITHUB_TOKEN": "github",
        "TERM": "xterm-256color",
        "LANG": "en_GB.UTF-8",
    }


def test_resolve_ssh_auth_sock_with_valid_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return the canonical path when SSH_AUTH_SOCK points to a live socket."""
    sock_path = (tmp_path / "agent.sock").resolve()

    def fake_stat(self: Path) -> SimpleNamespace:
        """Report the configured path as a Unix socket."""
        if self == sock_path:
            return SimpleNamespace(st_mode=stat.S_IFSOCK)
        raise OSError("missing")

    monkeypatch.setattr(Path, "stat", fake_stat)

    assert resolve_ssh_auth_sock(
        {"SSH_AUTH_SOCK": str(sock_path)},
        host_platform="Linux",
    ) == sock_path


def test_resolve_ssh_auth_sock_uses_host_services_socket_on_darwin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the runtime-provided host-services socket on macOS hosts."""
    sock_path = (tmp_path / "agent.sock").resolve()

    def fake_stat(self: Path) -> SimpleNamespace:
        """Report the configured path as a Unix socket."""
        if self == sock_path:
            return SimpleNamespace(st_mode=stat.S_IFSOCK)
        raise OSError("missing")

    monkeypatch.setattr(Path, "stat", fake_stat)

    assert resolve_ssh_auth_sock(
        {"SSH_AUTH_SOCK": str(sock_path)},
        host_platform="Darwin",
    ) == Path(HOST_SERVICES_SSH_AUTH_SOCK)


def test_resolve_ssh_auth_sock_rejects_missing_or_invalid_paths(tmp_path: Path) -> None:
    """Ignore missing, empty, and non-socket SSH agent paths."""
    file_path = tmp_path / "agent.txt"
    file_path.write_text("not a socket", encoding="utf-8")

    assert resolve_ssh_auth_sock({}) is None
    assert resolve_ssh_auth_sock({"SSH_AUTH_SOCK": ""}) is None
    assert resolve_ssh_auth_sock({"SSH_AUTH_SOCK": str(tmp_path / "missing.sock")}) is None
    assert resolve_ssh_auth_sock({"SSH_AUTH_SOCK": str(file_path)}) is None
