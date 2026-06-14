from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from forge.errors import ValidationError
from forge.models import VolumeMount
from forge.mounts import parse_volume_spec, validate_volume_targets


def test_parse_volume_spec_default_mode(tmp_path: Path) -> None:
    parsed = parse_volume_spec("./cache:/cache", tmp_path)

    assert parsed.host_path == (tmp_path / "cache").resolve()
    assert parsed.container_path.as_posix() == "/cache"
    assert parsed.mode == "rw"


def test_parse_volume_spec_ro_mode(tmp_path: Path) -> None:
    parsed = parse_volume_spec("/tmp/cache:/cache:ro", tmp_path)

    assert parsed.host_path == Path("/tmp/cache").resolve()
    assert parsed.mode == "ro"


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
    with pytest.raises(ValidationError):
        parse_volume_spec(spec, tmp_path)


def test_validate_volume_targets_rejects_reserved_path(tmp_path: Path) -> None:
    mount = VolumeMount(
        host_path=tmp_path / "cache",
        container_path=PurePosixPath("/workspace"),
        mode="rw",
    )

    with pytest.raises(ValidationError):
        validate_volume_targets((mount,))
