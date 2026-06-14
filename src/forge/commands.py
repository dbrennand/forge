from __future__ import annotations

from forge.config import CONTAINER_WORKSPACE


def build_shell_command() -> tuple[str, ...]:
    """Build the container command for an interactive shell session.

    Returns:
        tuple[str, ...]: Command arguments passed to Docker.
    """
    return ("/bin/bash",)


def build_codex_command(*, yolo: bool, skip_git_repo_check: bool) -> tuple[str, ...]:
    """Build the container command for interactive Codex sessions.

    Args:
        yolo: Whether to bypass approvals and nested sandboxing.
        skip_git_repo_check: Whether to skip Codex's git repository validation.

    Returns:
        tuple[str, ...]: Command arguments passed to Docker.
    """
    command = ["codex", "--cd", CONTAINER_WORKSPACE]
    if yolo:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        command.extend(["--sandbox", "workspace-write", "--ask-for-approval", "on-request"])
    if skip_git_repo_check:
        command.append("--skip-git-repo-check")
    return tuple(command)


def build_run_command(prompt: str, *, yolo: bool, skip_git_repo_check: bool) -> tuple[str, ...]:
    """Build the container command for non-interactive Codex execution.

    Args:
        prompt: Prompt forwarded to `codex exec`.
        yolo: Whether to bypass approvals and nested sandboxing.
        skip_git_repo_check: Whether to skip Codex's git repository validation.

    Returns:
        tuple[str, ...]: Command arguments passed to Docker.
    """
    command = ["codex", "exec", "--cd", CONTAINER_WORKSPACE]
    if yolo:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        command.extend(["--sandbox", "workspace-write"])
    if skip_git_repo_check:
        command.append("--skip-git-repo-check")
    command.extend(["--ephemeral", prompt])
    return tuple(command)
