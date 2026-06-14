from __future__ import annotations

from pathlib import Path

import pytest

from forge.errors import ValidationError
from forge.validation import (
    detect_git_repository,
    resolve_workspace,
    validate_codex_home,
    validate_gh_config,
    validate_host_identity,
)


def test_resolve_workspace_missing(tmp_path: Path) -> None:
    """Reject workspaces that do not exist."""
    with pytest.raises(ValidationError):
        resolve_workspace(tmp_path / "missing")


def test_resolve_workspace_not_directory(tmp_path: Path) -> None:
    """Reject workspaces that point to regular files."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("data", encoding="utf-8")

    with pytest.raises(ValidationError):
        resolve_workspace(file_path)


def test_validate_codex_home(tmp_path: Path) -> None:
    """Accept a Codex home that contains the auth file."""
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")

    assert validate_codex_home(tmp_path) == codex_home


def test_validate_codex_home_missing_auth(tmp_path: Path) -> None:
    """Reject a Codex home that lacks the auth file."""
    (tmp_path / ".codex").mkdir()

    with pytest.raises(ValidationError):
        validate_codex_home(tmp_path)


def test_validate_gh_config(tmp_path: Path) -> None:
    """Accept an existing GitHub CLI config directory."""
    gh_config = tmp_path / ".config" / "gh"
    gh_config.mkdir(parents=True)

    assert validate_gh_config(tmp_path) == gh_config


def test_validate_gh_config_missing(tmp_path: Path) -> None:
    """Reject a missing GitHub CLI config directory."""
    with pytest.raises(ValidationError):
        validate_gh_config(tmp_path)


def test_detect_git_repository_directory(tmp_path: Path) -> None:
    """Detect a repository when `.git` is a directory."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    assert detect_git_repository(workspace) is True


def test_detect_git_repository_worktree_file(tmp_path: Path) -> None:
    """Detect a repository when `.git` is a worktree pointer file."""
    gitdir = tmp_path / "worktree-git"
    gitdir.mkdir()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert detect_git_repository(workspace) is True


def test_detect_git_repository_worktree_file_requires_directory(tmp_path: Path) -> None:
    """Reject worktree pointers that do not resolve to directories."""
    gitdir = tmp_path / "worktree-git"
    gitdir.write_text("not a directory", encoding="utf-8")
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert detect_git_repository(workspace) is False


def test_detect_git_repository_invalid_git_file_encoding(tmp_path: Path) -> None:
    """Reject invalid `.git` file encodings."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").write_bytes(b"\xff")

    assert detect_git_repository(workspace) is False


def test_detect_git_repository_invalid_git_file(tmp_path: Path) -> None:
    """Reject `.git` files that are not valid worktree pointers."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").write_text("not-a-pointer\n", encoding="utf-8")

    assert detect_git_repository(workspace) is False


def test_validate_host_identity_rejects_root() -> None:
    """Reject execution as the root user or group."""
    with pytest.raises(ValidationError):
        validate_host_identity(0, 20)
