from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

MountMode = Literal["ro", "rw"]
CommandName = Literal["run", "codex", "shell"]


@dataclass(frozen=True)
class VolumeMount:
    """Describe one extra bind mount requested by the user.

    Attributes:
        host_path: Absolute host path mounted into the container.
        container_path: Absolute destination path inside the container.
        mode: Docker bind mode for the mount.
    """

    host_path: Path
    container_path: PurePosixPath
    mode: MountMode


@dataclass(frozen=True)
class CommonOptions:
    """Common CLI options shared by all Forge commands.

    Attributes:
        workspace: Host workspace path mounted into the container.
        image: Optional runtime image override.
        keep_container: Whether to leave the container behind after it exits.
        volume_specs: Raw extra volume specifications from the CLI.
    """

    workspace: Path
    image: str | None
    keep_container: bool
    volume_specs: tuple[str, ...]


@dataclass(frozen=True)
class RunOptions(CommonOptions):
    """CLI options for the non-interactive `forge run` command.

    Attributes:
        yolo: Whether to bypass approvals and nested sandboxing.
        prompt: Prompt forwarded to `codex exec`.
        command_name: Stable command identifier used downstream.
    """

    yolo: bool
    prompt: str
    command_name: Literal["run"] = field(default="run", init=False)


@dataclass(frozen=True)
class CodexOptions(CommonOptions):
    """CLI options for the interactive `forge codex` command.

    Attributes:
        yolo: Whether to bypass approvals and nested sandboxing.
        command_name: Stable command identifier used downstream.
    """

    yolo: bool
    command_name: Literal["codex"] = field(default="codex", init=False)


@dataclass(frozen=True)
class ShellOptions(CommonOptions):
    """CLI options for the interactive `forge shell` command.

    Attributes:
        command_name: Stable command identifier used downstream.
    """

    command_name: Literal["shell"] = field(default="shell", init=False)


@dataclass(frozen=True)
class ContainerRequest:
    """Describe a fully resolved Docker container execution request.

    Attributes:
        command_name: Forge subcommand being executed.
        image: Docker image reference to run.
        workspace: Host workspace mounted into the container.
        keep_container: Whether to retain the container after exit.
        extra_mounts: Additional validated bind mounts requested by the user.
        forwarded_env: Host environment variables forwarded into the container.
        command: Command executed inside the container.
        interactive: Whether the container should attach an interactive TTY.
        host_codex_dir: Host Codex directory mounted into the container.
        host_codex_config_file: Prepared Forge-managed Codex config path, if any.
        host_codex_hooks_file: Prepared Forge-managed legacy hooks path, if any.
        host_gh_config_dir: Host GitHub CLI config directory mounted read-only.
        host_ssh_auth_sock: Host-side SSH agent mount source used for the container, if any.
        host_uid: Host user identifier forwarded to the container.
        host_gid: Host group identifier forwarded to the container.
        nested_sandbox: Whether the inner Codex process needs relaxed container security.
        prepared_mount_dirs: Temporary directories that Forge should remove after
            container execution completes.
    """

    command_name: CommandName
    image: str
    workspace: Path
    keep_container: bool
    extra_mounts: tuple[VolumeMount, ...]
    forwarded_env: dict[str, str]
    command: tuple[str, ...]
    interactive: bool
    host_codex_dir: Path
    host_codex_config_file: Path | None
    host_codex_hooks_file: Path | None
    host_gh_config_dir: Path
    host_ssh_auth_sock: Path | None
    host_uid: int
    host_gid: int
    nested_sandbox: bool
    prepared_mount_dirs: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def auto_remove(self) -> bool:
        """Whether Docker should automatically remove the container after exit.

        Returns:
            bool: `True` when the container should be auto-removed.
        """
        return not self.keep_container
