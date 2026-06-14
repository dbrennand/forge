from __future__ import annotations

import signal
from pathlib import Path, PurePosixPath

from forge.docker_api import build_container_kwargs, signal_to_docker_name
from forge.models import ContainerRequest, VolumeMount


def make_request(tmp_path: Path, *, keep_container: bool = False) -> ContainerRequest:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex = tmp_path / ".codex"
    codex.mkdir()
    gh = tmp_path / ".config" / "gh"
    gh.mkdir(parents=True)
    return ContainerRequest(
        command_name="run",
        image="image:tag",
        workspace=workspace,
        keep_container=keep_container,
        extra_mounts=(
            VolumeMount(
                host_path=tmp_path / "cache",
                container_path=PurePosixPath("/cache"),
                mode="ro",
            ),
        ),
        forwarded_env={"GITHUB_TOKEN": "token"},
        command=("codex", "exec"),
        interactive=False,
        host_codex_dir=codex,
        host_gh_config_dir=gh,
        host_uid=501,
        host_gid=20,
    )


def test_build_container_kwargs(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    kwargs = build_container_kwargs(request)

    assert kwargs["auto_remove"] is True
    assert kwargs["working_dir"] == "/workspace"
    assert kwargs["environment"]["HOME"] == "/home/forge"
    assert kwargs["environment"]["CODEX_HOME"] == "/home/forge/.codex"
    assert kwargs["environment"]["FORGE_HOST_UID"] == "501"
    assert kwargs["volumes"][str(request.workspace)]["bind"] == "/workspace"
    assert kwargs["volumes"][str(request.host_codex_dir)]["bind"] == "/home/forge/.codex"
    assert kwargs["volumes"][str(request.host_gh_config_dir)]["mode"] == "ro"
    assert kwargs["labels"]["io.dbrennand.forge.command"] == "run"


def test_build_container_kwargs_keep_container(tmp_path: Path) -> None:
    request = make_request(tmp_path, keep_container=True)
    kwargs = build_container_kwargs(request)
    assert kwargs["auto_remove"] is False


def test_signal_to_docker_name() -> None:
    assert signal_to_docker_name(signal.SIGINT) == "SIGINT"
    assert signal_to_docker_name(signal.SIGTERM) == "SIGTERM"
    assert signal_to_docker_name(signal.SIGHUP) == "SIGHUP"
