from __future__ import annotations

from forge.commands import build_codex_command, build_run_command, build_shell_command


def test_build_shell_command() -> None:
    assert build_shell_command() == ("/bin/bash",)


def test_build_codex_command_default() -> None:
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
    assert build_codex_command(yolo=True, skip_git_repo_check=True) == (
        "codex",
        "--cd",
        "/workspace",
        "--yolo",
        "--skip-git-repo-check",
    )


def test_build_run_command_default() -> None:
    assert build_run_command("fix it", yolo=False, skip_git_repo_check=False) == (
        "codex",
        "exec",
        "--cd",
        "/workspace",
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
        "--ephemeral",
        "fix it",
    )


def test_build_run_command_yolo_and_skip_git() -> None:
    assert build_run_command("fix it", yolo=True, skip_git_repo_check=True) == (
        "codex",
        "exec",
        "--cd",
        "/workspace",
        "--yolo",
        "--skip-git-repo-check",
        "--ephemeral",
        "fix it",
    )
