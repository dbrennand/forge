from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from forge.args import parse_cli_args
from forge.codex_config import prepare_container_config
from forge.commands import build_codex_command, build_run_command, build_shell_command
from forge.docker_api import DockerRunner
from forge.env import collect_forwarded_env, resolve_image
from forge.errors import ForgeError
from forge.models import CodexOptions, ContainerRequest, RunOptions, ShellOptions
from forge.mounts import parse_volume_spec, validate_volume_sources, validate_volume_targets
from forge.validation import (
    detect_git_repository,
    resolve_workspace,
    validate_codex_home,
    validate_gh_config,
    validate_host_identity,
)


def build_container_request(
    request: RunOptions | CodexOptions | ShellOptions,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
    uid: int | None = None,
    gid: int | None = None,
) -> ContainerRequest:
    """Build a validated container execution request from CLI options.

    Args:
        request: Parsed CLI options for the requested Forge command.
        environ: Environment mapping to inspect for image and forwarded variables.
        cwd: Working directory used to resolve relative volume sources.
        home: Host home directory used to locate Codex and GitHub configuration.
        uid: Host user identifier to expose inside the container.
        gid: Host group identifier to expose inside the container.

    Returns:
        ContainerRequest: Fully resolved container request ready for Docker execution.
    """
    active_environ = dict(os.environ if environ is None else environ)
    active_cwd = Path.cwd() if cwd is None else cwd
    active_home = Path.home() if home is None else home
    active_uid = os.getuid() if uid is None else uid
    active_gid = os.getgid() if gid is None else gid

    workspace = resolve_workspace(request.workspace)
    validate_host_identity(active_uid, active_gid)
    host_codex_dir = validate_codex_home(active_home)
    host_codex_config_file = prepare_container_config(host_codex_dir)
    host_gh_config_dir = validate_gh_config(active_home)
    image = resolve_image(request.image, active_environ)
    extra_mounts = tuple(parse_volume_spec(spec, active_cwd) for spec in request.volume_specs)
    validate_volume_targets(extra_mounts)
    validate_volume_sources(
        extra_mounts,
        reserved_host_paths=(workspace, host_codex_dir, host_gh_config_dir),
    )
    skip_git_repo_check = not detect_git_repository(workspace)
    forwarded_env = collect_forwarded_env(active_environ)

    if isinstance(request, RunOptions):
        command = build_run_command(
            request.prompt,
            yolo=request.yolo,
            skip_git_repo_check=skip_git_repo_check,
        )
        interactive = False
        nested_sandbox = not request.yolo
    elif isinstance(request, CodexOptions):
        command = build_codex_command(yolo=request.yolo, skip_git_repo_check=skip_git_repo_check)
        interactive = True
        nested_sandbox = not request.yolo
    else:
        command = build_shell_command()
        interactive = True
        nested_sandbox = False

    return ContainerRequest(
        command_name=request.command_name,
        image=image,
        workspace=workspace,
        keep_container=request.keep_container,
        extra_mounts=extra_mounts,
        forwarded_env=forwarded_env,
        command=command,
        interactive=interactive,
        host_codex_dir=host_codex_dir,
        host_codex_config_file=host_codex_config_file,
        host_gh_config_dir=host_gh_config_dir,
        host_uid=active_uid,
        host_gid=active_gid,
        nested_sandbox=nested_sandbox,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
    runner: DockerRunner | None = None,
) -> int:
    """Run Forge for the provided CLI arguments.

    Args:
        argv: Optional CLI argument vector.
        environ: Environment mapping override for tests or embedding.
        cwd: Working directory override used for relative path resolution.
        home: Home directory override used for configuration discovery.
        runner: Optional Docker runner instance to reuse or substitute in tests.

    Returns:
        int: Process exit status from the container execution.
    """
    request = parse_cli_args(argv)
    container_request = build_container_request(
        request,
        environ=environ,
        cwd=cwd,
        home=home,
    )
    docker_runner = DockerRunner.from_env() if runner is None else runner
    docker_runner.ping()
    return docker_runner.execute(container_request)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Forge CLI entrypoint with user-facing error handling.

    Args:
        argv: Optional CLI argument vector.

    Returns:
        int: Exit code to return from the process.
    """
    try:
        return run(argv)
    except BrokenPipeError:
        return 141
    except ForgeError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
