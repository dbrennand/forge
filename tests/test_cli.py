from __future__ import annotations

from pathlib import Path

import pytest

from forge.cli import build_container_request
from forge.models import CodexOptions, RunOptions, ShellOptions


@pytest.fixture
def home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    gh_home = tmp_path / ".config" / "gh"
    gh_home.mkdir(parents=True)
    return tmp_path


def test_build_container_request_for_run(tmp_path: Path, home: Path) -> None:
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
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
        "--ephemeral",
        "do work",
    )
    assert container_request.forwarded_env == {"GITHUB_TOKEN": "token"}
    assert container_request.extra_mounts[0].container_path.as_posix() == "/cache"
    assert container_request.interactive is False


def test_build_container_request_for_git_workspace(tmp_path: Path, home: Path) -> None:
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

    assert container_request.command == ("codex", "--cd", "/workspace", "--yolo")
    assert container_request.keep_container is True
    assert container_request.interactive is True


def test_build_container_request_for_shell(tmp_path: Path, home: Path) -> None:
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
