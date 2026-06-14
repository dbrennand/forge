from __future__ import annotations

from pathlib import Path

from forge.errors import ValidationError


def resolve_workspace(workspace: Path) -> Path:
    """Resolve and validate the requested workspace directory.

    Args:
        workspace: User-supplied workspace path.

    Returns:
        Path: Absolute resolved workspace path.

    Raises:
        ValidationError: If the path does not exist or is not a directory.
    """
    resolved = workspace.expanduser().resolve()
    if not resolved.exists():
        raise ValidationError(f"Workspace does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValidationError(f"Workspace is not a directory: {resolved}")
    return resolved


def validate_codex_home(home: Path) -> Path:
    """Validate that the host Codex home contains required authentication state.

    Args:
        home: Host home directory.

    Returns:
        Path: Resolved `.codex` directory.

    Raises:
        ValidationError: If the auth file is missing.
    """
    codex_home = home.expanduser() / ".codex"
    auth_file = codex_home / "auth.json"
    if not auth_file.is_file():
        raise ValidationError(f"Missing Codex auth file: {auth_file}")
    return codex_home


def validate_gh_config(home: Path) -> Path:
    """Validate that the host GitHub CLI config directory exists.

    Args:
        home: Host home directory.

    Returns:
        Path: Resolved GitHub CLI config directory.

    Raises:
        ValidationError: If the directory is missing.
    """
    gh_config = home.expanduser() / ".config" / "gh"
    if not gh_config.is_dir():
        raise ValidationError(f"Missing GitHub CLI config directory: {gh_config}")
    return gh_config


def detect_git_repository(workspace: Path) -> bool:
    """Detect whether the workspace is backed by a Git repository or worktree.

    Args:
        workspace: Candidate workspace directory.

    Returns:
        bool: `True` when `.git` resolves to a repository directory.
    """
    dot_git = workspace / ".git"
    if dot_git.is_dir():
        return True
    if not dot_git.is_file():
        return False

    try:
        content = dot_git.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return False
    prefix = "gitdir:"
    if not content.startswith(prefix):
        return False
    pointer = content[len(prefix) :].strip()
    if not pointer:
        return False

    git_dir = Path(pointer)
    if not git_dir.is_absolute():
        git_dir = (workspace / git_dir).resolve()
    return git_dir.is_dir()


def validate_host_identity(uid: int, gid: int) -> None:
    """Reject Forge execution as the root user or group.

    Args:
        uid: Host user identifier.
        gid: Host group identifier.

    Raises:
        ValidationError: If Forge is invoked with root ownership.
    """
    if uid == 0 or gid == 0:
        raise ValidationError("Forge must be invoked as a non-root user")
