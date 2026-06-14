from __future__ import annotations

import signal
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from docker.errors import NotFound

from forge.docker_api import (
    DockerRunner,
    _close_attached_socket,
    _raw_attached_socket,
    build_container_kwargs,
    signal_to_docker_name,
)
from forge.errors import ContainerRuntimeError
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


def test_raw_attached_socket_uses_underlying_socket() -> None:
    raw_socket = object()
    attachment = SimpleNamespace(_sock=raw_socket)

    assert _raw_attached_socket(attachment) is raw_socket


def test_raw_attached_socket_accepts_socket_without_wrapper() -> None:
    raw_socket = object()

    assert _raw_attached_socket(raw_socket) is raw_socket


def test_close_attached_socket_closes_wrapper_response_before_attachment() -> None:
    events: list[str] = []

    class FakeAttachment:
        def __init__(self) -> None:
            self.closed = False
            self._sock = SimpleNamespace()
            self._response: object | None = None

        def close(self) -> None:
            self.closed = True
            events.append("attachment.close")

    attachment = FakeAttachment()

    class FakeResponse:
        def close(self) -> None:
            if attachment.closed:
                raise AssertionError("response closed after attachment")
            events.append("response.close")

    attachment._response = FakeResponse()

    _close_attached_socket(attachment)

    assert events == ["response.close", "attachment.close"]
    assert not hasattr(attachment, "_response")
    assert not hasattr(attachment._sock, "_response")


def test_close_attached_socket_closes_raw_socket_response_before_attachment() -> None:
    events: list[str] = []

    class FakeAttachment:
        def __init__(self) -> None:
            self.closed = False
            self._sock = SimpleNamespace()

        def close(self) -> None:
            self.closed = True
            events.append("attachment.close")

    attachment = FakeAttachment()

    class FakeResponse:
        def close(self) -> None:
            if attachment.closed:
                raise AssertionError("response closed after attachment")
            events.append("response.close")

    attachment._sock._response = FakeResponse()

    _close_attached_socket(attachment)

    assert events == ["response.close", "attachment.close"]
    assert not hasattr(attachment._sock, "_response")


def test_wait_for_container_uses_cached_exit_code_after_auto_remove() -> None:
    runner = DockerRunner(client=object())

    class FakeContainer:
        attrs: dict[str, dict[str, int]] = {"State": {"ExitCode": 0}}

        def wait(self) -> object:
            raise NotFound("missing")

    assert runner._wait_for_container(FakeContainer()) == 0


def test_wait_for_container_requires_cached_exit_code_when_missing() -> None:
    runner = DockerRunner(client=object())

    class FakeContainer:
        attrs: dict[str, dict[str, int]] = {"State": {}}

        def wait(self) -> object:
            raise NotFound("missing")

    with pytest.raises(ContainerRuntimeError):
        runner._wait_for_container(FakeContainer())
