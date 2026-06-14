from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

MountMode = Literal["ro", "rw"]
CommandName = Literal["run", "codex", "shell"]


@dataclass(frozen=True)
class VolumeMount:
    host_path: Path
    container_path: PurePosixPath
    mode: MountMode


@dataclass(frozen=True)
class CommonOptions:
    workspace: Path
    image: str | None
    keep_container: bool
    volume_specs: tuple[str, ...]


@dataclass(frozen=True)
class RunOptions(CommonOptions):
    yolo: bool
    prompt: str
    command_name: Literal["run"] = field(default="run", init=False)


@dataclass(frozen=True)
class CodexOptions(CommonOptions):
    yolo: bool
    command_name: Literal["codex"] = field(default="codex", init=False)


@dataclass(frozen=True)
class ShellOptions(CommonOptions):
    command_name: Literal["shell"] = field(default="shell", init=False)


@dataclass(frozen=True)
class ContainerRequest:
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
    host_gh_config_dir: Path
    host_uid: int
    host_gid: int
    nested_sandbox: bool

    @property
    def auto_remove(self) -> bool:
        return not self.keep_container
