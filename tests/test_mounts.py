from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from forge.errors import ValidationError
from forge.models import VolumeMount
from forge.mounts import parse_volume_spec, validate_volume_sources, validate_volume_targets


def test_parse_volume_spec_default_mode(tmp_path: Path) -> None:
    """Default volume specs to read-write mode."""
    parsed = parse_volume_spec("./cache:/cache", tmp_path)

    assert parsed.host_path == (tmp_path / "cache").resolve()
    assert parsed.container_path.as_posix() == "/cache"
    assert parsed.mode == "rw"


def test_parse_volume_spec_ro_mode(tmp_path: Path) -> None:
    """Preserve an explicit read-only mount mode."""
    parsed = parse_volume_spec("/tmp/cache:/cache:ro", tmp_path)

    assert parsed.host_path == Path("/tmp/cache").resolve()
    assert parsed.mode == "ro"


def test_parse_volume_spec_normalizes_container_path(tmp_path: Path) -> None:
    """Normalize container mount paths before storing them."""
    parsed = parse_volume_spec("./cache:/workspace/../cache", tmp_path)

    assert parsed.container_path == PurePosixPath("/cache")


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "cache",
        "cache:relative",
        "cache:/data:invalid",
    ],
)
def test_parse_volume_spec_invalid(spec: str, tmp_path: Path) -> None:
    """Reject malformed volume specifications."""
    with pytest.raises(ValidationError):
        parse_volume_spec(spec, tmp_path)


def test_validate_volume_targets_rejects_reserved_path(tmp_path: Path) -> None:
    """Reject extra mounts that target reserved container paths."""
    mount = VolumeMount(
        host_path=tmp_path / "cache",
        container_path=PurePosixPath("/workspace"),
        mode="rw",
    )

    with pytest.raises(ValidationError):
        validate_volume_targets((mount,))


def test_validate_volume_targets_rejects_overlapping_extra_targets(tmp_path: Path) -> None:
    """Reject extra mounts whose target paths overlap each other."""
    mounts = (
        VolumeMount(
            host_path=tmp_path / "cache-a",
            container_path=PurePosixPath("/cache"),
            mode="rw",
        ),
        VolumeMount(
            host_path=tmp_path / "cache-b",
            container_path=PurePosixPath("/cache/subdir"),
            mode="rw",
        ),
    )

    with pytest.raises(ValidationError):
        validate_volume_targets(mounts)


def test_validate_volume_sources_rejects_duplicate_host_path(tmp_path: Path) -> None:
    """Reject repeated extra mount source paths on the host."""
    shared_host_path = tmp_path / "cache"
    mounts = (
        VolumeMount(
            host_path=shared_host_path,
            container_path=PurePosixPath("/cache-a"),
            mode="rw",
        ),
        VolumeMount(
            host_path=shared_host_path,
            container_path=PurePosixPath("/cache-b"),
            mode="ro",
        ),
    )

    with pytest.raises(ValidationError):
        validate_volume_sources(mounts, reserved_host_paths=())


@pytest.mark.parametrize(
    ("first_source", "second_source"),
    [
        ("cache", "cache/subdir"),
        ("cache/subdir", "cache"),
    ],
)
def test_validate_volume_sources_rejects_overlapping_extra_sources(
    tmp_path: Path,
    first_source: str,
    second_source: str,
) -> None:
    """Reject extra mount source paths that overlap by ancestry."""
    first_path = tmp_path / first_source
    second_path = tmp_path / second_source
    mounts = (
        VolumeMount(
            host_path=first_path,
            container_path=PurePosixPath("/cache-a"),
            mode="rw",
        ),
        VolumeMount(
            host_path=second_path,
            container_path=PurePosixPath("/cache-b"),
            mode="ro",
        ),
    )

    with pytest.raises(ValidationError):
        validate_volume_sources(mounts, reserved_host_paths=())


def test_validate_volume_sources_rejects_reserved_host_path(tmp_path: Path) -> None:
    """Reject extra mounts that reuse reserved Forge host paths."""
    reserved_path = tmp_path / "workspace"
    mount = VolumeMount(
        host_path=reserved_path,
        container_path=PurePosixPath("/cache"),
        mode="rw",
    )

    with pytest.raises(ValidationError):
        validate_volume_sources((mount,), reserved_host_paths=(reserved_path,))


@pytest.mark.parametrize(
    ("source", "reserved"),
    [
        ("home", "home/.codex"),
        ("home/.config", "home/.config/gh"),
        ("home/.codex/auth.json", "home/.codex"),
        ("workspace/subdir", "workspace"),
        ("agent-parent", "agent-parent/agent.sock"),
    ],
)
def test_validate_volume_sources_rejects_reserved_host_path_overlap(
    tmp_path: Path,
    source: str,
    reserved: str,
) -> None:
    """Reject extra mount sources that contain or sit inside reserved host paths."""
    source_path = tmp_path / source
    reserved_path = tmp_path / reserved
    mount = VolumeMount(
        host_path=source_path,
        container_path=PurePosixPath("/cache"),
        mode="rw",
    )

    with pytest.raises(ValidationError):
        validate_volume_sources((mount,), reserved_host_paths=(reserved_path,))
