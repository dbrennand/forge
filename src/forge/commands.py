from __future__ import annotations

from forge.config import CONTAINER_WORKSPACE


def build_shell_command() -> tuple[str, ...]:
    return ("/bin/bash",)


def build_codex_command(*, yolo: bool, skip_git_repo_check: bool) -> tuple[str, ...]:
    command = ["codex", "--cd", CONTAINER_WORKSPACE]
    if yolo:
        command.append("--yolo")
    else:
        command.extend(["--sandbox", "workspace-write", "--ask-for-approval", "on-request"])
    if skip_git_repo_check:
        command.append("--skip-git-repo-check")
    return tuple(command)


def build_run_command(prompt: str, *, yolo: bool, skip_git_repo_check: bool) -> tuple[str, ...]:
    command = ["codex", "exec", "--cd", CONTAINER_WORKSPACE]
    if yolo:
        command.append("--yolo")
    else:
        command.extend(["--sandbox", "workspace-write", "--ask-for-approval", "never"])
    if skip_git_repo_check:
        command.append("--skip-git-repo-check")
    command.extend(["--ephemeral", prompt])
    return tuple(command)
