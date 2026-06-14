from __future__ import annotations

from pathlib import Path

import pytest

from forge.args import parse_cli_args
from forge.models import CodexOptions, RunOptions, ShellOptions


def test_parse_run_command() -> None:
    parsed = parse_cli_args(
        [
            "run",
            "--workspace",
            "/tmp/repo",
            "--image",
            "custom:image",
            "--keep-container",
            "--volume",
            "./cache:/cache:ro",
            "--yolo",
            "hello",
        ]
    )

    assert isinstance(parsed, RunOptions)
    assert parsed.workspace == Path("/tmp/repo")
    assert parsed.image == "custom:image"
    assert parsed.keep_container is True
    assert parsed.volume_specs == ("./cache:/cache:ro",)
    assert parsed.yolo is True
    assert parsed.prompt == "hello"


def test_parse_codex_command() -> None:
    parsed = parse_cli_args(["codex", "--yolo", "/tmp/repo"])

    assert isinstance(parsed, CodexOptions)
    assert parsed.workspace == Path("/tmp/repo")
    assert parsed.yolo is True


def test_parse_shell_command() -> None:
    parsed = parse_cli_args(["shell", "/tmp/repo"])

    assert isinstance(parsed, ShellOptions)
    assert parsed.workspace == Path("/tmp/repo")


def test_run_requires_workspace_option() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["run", "hello"])


def test_codex_requires_project_argument() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["codex"])
