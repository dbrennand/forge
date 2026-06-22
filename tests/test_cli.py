from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from forge.cli import build_container_request, run
from forge.docker_api import DockerRunner
from forge.errors import ValidationError
from forge.models import CodexOptions, ContainerRequest, RunOptions, ShellOptions


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Create a minimal fake home directory with Codex and GitHub config."""
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    (codex_home / "config.toml").write_text('model = "gpt-5.5"\n', encoding="utf-8")
    gh_home = tmp_path / ".config" / "gh"
    gh_home.mkdir(parents=True)
    return tmp_path


def test_build_container_request_for_run(tmp_path: Path, home: Path) -> None:
    """Build a non-interactive container request from run options."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    request = RunOptions(
        workspace=workspace,
        image=None,
        keep_container=False,
        volume_specs=("./cache:/cache:ro",),
        yolo=False,
        prompt="do work",
    )

    container_request = build_container_request(
        request,
        environ={"FORGE_IMAGE": "env:image", "GITHUB_TOKEN": "token"},
        cwd=tmp_path,
        home=home,
        uid=501,
        gid=20,
    )

    assert container_request.image == "env:image"
    assert container_request.command == (
        "codex",
        "exec",
        "--cd",
        "/workspace",
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--ephemeral",
        "do work",
    )
    assert container_request.forwarded_env == {"GITHUB_TOKEN": "token"}
    assert container_request.extra_mounts[0].container_path.as_posix() == "/cache"
    assert container_request.interactive is False
    assert container_request.host_codex_config_file is not None
    assert container_request.host_codex_config_file == home / ".codex" / "forge" / "config.toml"
    assert container_request.host_codex_hooks_file is None
    assert container_request.prepared_mount_dirs == ()
    assert container_request.host_ssh_auth_sock is None
    assert container_request.nested_sandbox is True


def test_build_container_request_for_git_workspace(tmp_path: Path, home: Path) -> None:
    """Build an interactive Codex request without skipping git checks for repos."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    request = CodexOptions(
        workspace=workspace,
        image="image:tag",
        keep_container=True,
        volume_specs=(),
        yolo=True,
    )

    container_request = build_container_request(request, cwd=tmp_path, home=home, uid=501, gid=20)

    assert container_request.command == (
        "codex",
        "--cd",
        "/workspace",
        "--dangerously-bypass-approvals-and-sandbox",
    )
    assert container_request.keep_container is True
    assert container_request.interactive is True
    assert container_request.host_codex_config_file == home / ".codex" / "forge" / "config.toml"
    assert container_request.host_codex_hooks_file is None
    assert container_request.prepared_mount_dirs == ()
    assert container_request.nested_sandbox is False


def test_build_container_request_for_shell(tmp_path: Path, home: Path) -> None:
    """Build an interactive shell request without nested sandboxing."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    request = ShellOptions(
        workspace=workspace,
        image="image:tag",
        keep_container=False,
        volume_specs=(),
    )

    container_request = build_container_request(request, cwd=tmp_path, home=home, uid=501, gid=20)

    assert container_request.command == ("/bin/bash",)
    assert container_request.host_codex_config_file is not None
    assert container_request.host_codex_config_file == home / ".codex" / "forge" / "config.toml"
    assert container_request.host_codex_hooks_file is None
    assert container_request.prepared_mount_dirs == ()
    assert container_request.nested_sandbox is False


def test_build_container_request_mounts_managed_legacy_hooks_when_host_file_contains_hooks(
    tmp_path: Path, home: Path
) -> None:
    """Mount the Forge-managed legacy hooks file only when legacy hooks remain."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (home / ".codex" / "hooks.json").write_text(
        '{"hooks":{"SessionStart":[{"hooks":[{"command":"other-hook"}]}]}}',
        encoding="utf-8",
    )
    request = CodexOptions(
        workspace=workspace,
        image="image:tag",
        keep_container=False,
        volume_specs=(),
        yolo=False,
    )

    container_request = build_container_request(request, cwd=tmp_path, home=home, uid=501, gid=20)

    assert container_request.host_codex_hooks_file == home / ".codex" / "forge" / "hooks.json"
    assert container_request.prepared_mount_dirs == ()


def test_run_leaves_persistent_codex_managed_files_when_docker_ping_fails(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep persistent Forge-managed Codex files when startup fails early."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    captured: dict[str, ContainerRequest] = {}
    real_build_container_request = build_container_request

    def capture_request(*args: Any, **kwargs: Any) -> ContainerRequest:
        """Capture the built container request for post-failure assertions."""
        request = real_build_container_request(*args, **kwargs)
        captured["request"] = request
        return request

    class FailingClient:
        """Raise before container execution to exercise cleanup paths."""

        def ping(self) -> None:
            """Simulate Docker startup failure."""
            raise RuntimeError("docker unavailable")

    monkeypatch.setattr("forge.cli.build_container_request", capture_request)
    monkeypatch.setattr("forge.cli.os.getuid", lambda: 501)
    monkeypatch.setattr("forge.cli.os.getgid", lambda: 20)

    with pytest.raises(RuntimeError, match="docker unavailable"):
        run(
            ["codex", str(workspace)],
            home=home,
            cwd=tmp_path,
            runner=DockerRunner(client=FailingClient()),
        )

    container_request = captured["request"]
    managed_dir = home / ".codex" / "forge"
    assert container_request.prepared_mount_dirs == ()
    assert managed_dir.is_dir()
    assert (managed_dir / "config.toml").is_file()


def test_build_container_request_captures_ssh_agent_socket(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capture a valid host SSH agent socket as a Forge-managed mount."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    sock_path = tmp_path / "agent.sock"
    monkeypatch.setattr("forge.cli.resolve_ssh_auth_sock", lambda environ: sock_path.resolve())
    request = ShellOptions(
        workspace=workspace,
        image="image:tag",
        keep_container=False,
        volume_specs=(),
    )

    container_request = build_container_request(
        request,
        environ={"SSH_AUTH_SOCK": str(sock_path)},
        cwd=tmp_path,
        home=home,
        uid=501,
        gid=20,
    )

    assert container_request.host_ssh_auth_sock == sock_path.resolve()


def test_build_container_request_ignores_invalid_ssh_agent_socket(
    tmp_path: Path, home: Path
) -> None:
    """Ignore invalid SSH_AUTH_SOCK values without failing request construction."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    invalid_path = tmp_path / "not-a-socket"
    invalid_path.write_text("x", encoding="utf-8")
    request = ShellOptions(
        workspace=workspace,
        image="image:tag",
        keep_container=False,
        volume_specs=(),
    )

    container_request = build_container_request(
        request,
        environ={"SSH_AUTH_SOCK": str(invalid_path)},
        cwd=tmp_path,
        home=home,
        uid=501,
        gid=20,
    )

    assert container_request.host_ssh_auth_sock is None


def test_build_container_request_rejects_reserved_volume_target_bypass(
    tmp_path: Path, home: Path
) -> None:
    """Reject extra mounts that normalize into reserved container paths."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    request = RunOptions(
        workspace=workspace,
        image=None,
        keep_container=False,
        volume_specs=("./cache:/workspace/../home/forge/.codex",),
        yolo=False,
        prompt="do work",
    )

    with pytest.raises(ValidationError):
        build_container_request(request, cwd=tmp_path, home=home, uid=501, gid=20)


def test_build_container_request_rejects_reserved_host_volume_source(
    tmp_path: Path, home: Path
) -> None:
    """Reject extra mounts that reuse reserved host source paths."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    request = RunOptions(
        workspace=workspace,
        image=None,
        keep_container=False,
        volume_specs=(f"{workspace}:/cache",),
        yolo=False,
        prompt="do work",
    )

    with pytest.raises(ValidationError):
        build_container_request(request, cwd=tmp_path, home=home, uid=501, gid=20)


def test_build_container_request_rejects_ssh_agent_host_volume_source(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject extra mounts that reuse the active SSH agent socket path."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    sock_path = tmp_path / "agent.sock"
    monkeypatch.setattr("forge.cli.resolve_ssh_auth_sock", lambda environ: sock_path.resolve())
    request = RunOptions(
        workspace=workspace,
        image=None,
        keep_container=False,
        volume_specs=(f"{sock_path}:/agent.sock",),
        yolo=False,
        prompt="do work",
    )

    with pytest.raises(ValidationError):
        build_container_request(
            request,
            environ={"SSH_AUTH_SOCK": str(sock_path)},
            cwd=tmp_path,
            home=home,
            uid=501,
            gid=20,
        )
