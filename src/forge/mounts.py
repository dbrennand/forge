from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import cast

from forge.config import RESERVED_MOUNT_PATHS
from forge.errors import ValidationError
from forge.models import MountMode, VolumeMount


def parse_volume_spec(spec: str, cwd: Path) -> VolumeMount:
    """Parse one CLI volume specification into a validated mount model.

    Args:
        spec: Raw `HOST:CTR[:ro|rw]` volume specification.
        cwd: Working directory used to resolve relative host paths.

    Returns:
        VolumeMount: Parsed bind mount description.

    Raises:
        ValidationError: If the specification is malformed.
    """
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
    container_path = _normalize_container_path(container_segment)

    return VolumeMount(
        host_path=host_path,
        container_path=container_path,
        mode=mode,
    )


def validate_volume_targets(mounts: tuple[VolumeMount, ...]) -> None:
    """Ensure extra mount targets do not overlap reserved or duplicate paths.

    Args:
        mounts: Extra container mounts requested by the user.

    Raises:
        ValidationError: If any target overlaps another extra mount or a reserved path.
    """
    checked_mounts: list[VolumeMount] = []
    for mount in mounts:
        for checked_mount in checked_mounts:
            if _paths_overlap(mount.container_path, checked_mount.container_path):
                raise ValidationError(
                    "Extra volume target "
                    f"{mount.container_path.as_posix()} overlaps extra volume target "
                    f"{checked_mount.container_path.as_posix()}"
                )
        for reserved in RESERVED_MOUNT_PATHS:
            if _paths_overlap(mount.container_path, reserved):
                raise ValidationError(
                    "Extra volume target "
                    f"{mount.container_path.as_posix()} overlaps reserved path "
                    f"{reserved.as_posix()}"
                )
        checked_mounts.append(mount)


def validate_volume_sources(
    mounts: tuple[VolumeMount, ...], *, reserved_host_paths: tuple[Path, ...]
) -> None:
    """Ensure extra mount sources do not duplicate reserved or repeated host paths.

    Args:
        mounts: Extra container mounts requested by the user.
        reserved_host_paths: Host paths already used for Forge-managed mounts.

    Raises:
        ValidationError: If any source path duplicates another source or a reserved path.
    """
    seen_host_paths: set[Path] = set()
    reserved_sources = set(reserved_host_paths)

    for mount in mounts:
        if mount.host_path in seen_host_paths:
            raise ValidationError(f"Duplicate host volume source: {mount.host_path}")
        if mount.host_path in reserved_sources:
            raise ValidationError(
                f"Extra volume source {mount.host_path} overlaps a reserved host path"
            )
        seen_host_paths.add(mount.host_path)


def _paths_overlap(left: PurePosixPath, right: PurePosixPath) -> bool:
    """Report whether two container paths overlap by ancestry or equality.

    Args:
        left: First container path.
        right: Second container path.

    Returns:
        bool: `True` when either path contains the other.
    """
    return left == right or left in right.parents or right in left.parents


def _normalize_container_path(raw_path: str) -> PurePosixPath:
    """Normalize a raw container path without touching the host filesystem.

    Args:
        raw_path: Raw container path from the CLI.

    Returns:
        PurePosixPath: Normalized absolute container path.
    """
    segments: list[str] = []
    for segment in raw_path.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)

    if not segments:
        return PurePosixPath("/")
    return PurePosixPath("/", *segments)
