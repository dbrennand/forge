from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from forge.models import CodexOptions, RunOptions, ShellOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = _add_common_options(
        subparsers.add_parser("run", help="Run Codex non-interactively")
    )
    run_parser.add_argument("--yolo", action="store_true", help="Run Codex with --yolo")
    run_parser.add_argument("prompt", help="Prompt passed to codex exec")

    codex_parser = _add_common_options(subparsers.add_parser("codex", help="Run interactive Codex"))
    codex_parser.add_argument("--yolo", action="store_true", help="Run Codex with --yolo")

    _add_common_options(subparsers.add_parser("shell", help="Run an interactive shell"))

    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> RunOptions | CodexOptions | ShellOptions:
    namespace = build_parser().parse_args(argv)
    volume_specs = tuple(namespace.volume or [])

    if namespace.command == "run":
        return RunOptions(
            workspace=namespace.workspace,
            image=namespace.image,
            keep_container=namespace.keep_container,
            volume_specs=volume_specs,
            yolo=namespace.yolo,
            prompt=namespace.prompt,
        )
    if namespace.command == "codex":
        return CodexOptions(
            workspace=namespace.workspace,
            image=namespace.image,
            keep_container=namespace.keep_container,
            volume_specs=volume_specs,
            yolo=namespace.yolo,
        )
    return ShellOptions(
        workspace=namespace.workspace,
        image=namespace.image,
        keep_container=namespace.keep_container,
        volume_specs=volume_specs,
    )


def _add_common_options(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Workspace mounted into the container",
    )
    parser.add_argument("--image", help="Override the runtime image")
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep the container after exit",
    )
    parser.add_argument(
        "--volume",
        action="append",
        default=[],
        metavar="HOST:CTR[:ro|rw]",
        help="Additional bind mount",
    )
    return parser
