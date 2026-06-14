from __future__ import annotations

from forge.commands import build_codex_command, build_run_command, build_shell_command


def test_build_shell_command() -> None:
    """Build the shell command as a bare Bash invocation."""
    assert build_shell_command() == ("/bin/bash",)


def test_build_codex_command_default() -> None:
    """Build the default interactive Codex command with sandbox flags."""
    assert build_codex_command(yolo=False, skip_git_repo_check=False) == (
        "codex",
        "--cd",
        "/workspace",
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "on-request",
    )


def test_build_codex_command_yolo_and_skip_git() -> None:
    """Build the interactive Codex command with yolo and git-skip flags."""
    assert build_codex_command(yolo=True, skip_git_repo_check=True) == (
        "codex",
        "--cd",
        "/workspace",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
    )


def test_build_run_command_default() -> None:
    """Build the default non-interactive Codex exec command."""
    assert build_run_command("fix it", yolo=False, skip_git_repo_check=False) == (
        "codex",
        "exec",
        "--cd",
        "/workspace",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "fix it",
    )


def test_build_run_command_yolo_and_skip_git() -> None:
    """Build the non-interactive Codex exec command with yolo and git-skip flags."""
    assert build_run_command("fix it", yolo=True, skip_git_repo_check=True) == (
        "codex",
        "exec",
        "--cd",
        "/workspace",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--ephemeral",
        "fix it",
    )
