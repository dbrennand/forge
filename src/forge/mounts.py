from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import cast

from forge.config import RESERVED_MOUNT_PATHS
from forge.errors import ValidationError
from forge.models import MountMode, VolumeMount


def parse_volume_spec(spec: str, cwd: Path) -> VolumeMount:
    if not spec:
        raise ValidationError("Volume spec must not be empty")

    mode: MountMode = "rw"
    host_segment: str
    container_segment: str

    parts = spec.rsplit(":", 2)
    if len(parts) < 2:
        raise ValidationError(f"Malformed volume spec: {spec}")
    if parts[-1] in {"ro", "rw"} and len(parts) == 3:
        host_segment, container_segment, raw_mode = parts
        mode = cast(MountMode, raw_mode)
    elif parts[-1] in {"ro", "rw"} and len(parts) != 3:
        raise ValidationError(f"Malformed volume spec: {spec}")
    else:
        host_segment = ":".join(parts[:-1])
        container_segment = parts[-1]

    if not host_segment or not container_segment:
        raise ValidationError(f"Malformed volume spec: {spec}")
    if not container_segment.startswith("/"):
        raise ValidationError(f"Container mount path must be absolute: {container_segment}")

    host_path = Path(host_segment).expanduser()
    host_path = (cwd / host_path).resolve() if not host_path.is_absolute() else host_path.resolve()

    return VolumeMount(
        host_path=host_path,
        container_path=PurePosixPath(container_segment),
        mode=mode,
    )


def validate_volume_targets(mounts: tuple[VolumeMount, ...]) -> None:
    for mount in mounts:
        for reserved in RESERVED_MOUNT_PATHS:
            if _paths_overlap(mount.container_path, reserved):
                raise ValidationError(
                    "Extra volume target "
                    f"{mount.container_path.as_posix()} overlaps reserved path "
                    f"{reserved.as_posix()}"
                )


def _paths_overlap(left: PurePosixPath, right: PurePosixPath) -> bool:
    return left == right or left in right.parents or right in left.parents
