from __future__ import annotations

import os
import re
import signal
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from docker.errors import NotFound

from forge.config import CONTAINER_SSH_AUTH_SOCK
from forge.docker_api import (
    DockerRunner,
    _close_attached_socket,
    _raw_attached_socket,
    _SignalForwarder,
    _terminal_size,
    build_container_kwargs,
    signal_to_docker_name,
)
from forge.errors import ContainerRuntimeError
from forge.models import ContainerRequest, VolumeMount


def make_request(tmp_path: Path, *, keep_container: bool = False) -> ContainerRequest:
    """Build a representative container request for Docker API tests."""
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex = tmp_path / ".codex"
    codex.mkdir()
    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-5.5"\n', encoding="utf-8")
    gh = tmp_path / ".config" / "gh"
    gh.mkdir(parents=True)
    ssh_auth_sock = tmp_path / "agent.sock"
    ssh_auth_sock.write_text("", encoding="utf-8")
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
        host_codex_config_file=config,
        host_gh_config_dir=gh,
        host_ssh_auth_sock=ssh_auth_sock,
        host_uid=501,
        host_gid=20,
        nested_sandbox=True,
    )


def test_build_container_kwargs(tmp_path: Path) -> None:
    """Build Docker create kwargs including Forge-managed mounts and labels."""
    request = make_request(tmp_path)
    kwargs = build_container_kwargs(request)

    assert kwargs["auto_remove"] is True
    assert re.fullmatch(r"forge_\d+", kwargs["name"]) is not None
    assert kwargs["working_dir"] == "/workspace"
    assert kwargs["environment"]["HOME"] == "/home/forge"
    assert kwargs["environment"]["CODEX_HOME"] == "/home/forge/.codex"
    assert kwargs["environment"]["FORGE_HOST_UID"] == "501"
    assert kwargs["volumes"][str(request.workspace)]["bind"] == "/workspace"
    assert kwargs["volumes"][str(request.host_codex_dir)]["bind"] == "/home/forge/.codex"
    assert (
        kwargs["volumes"][str(request.host_codex_config_file)]["bind"]
        == "/home/forge/.codex/config.toml"
    )
    assert kwargs["volumes"][str(request.host_gh_config_dir)]["mode"] == "ro"
    assert kwargs["volumes"][str(request.host_ssh_auth_sock)]["bind"] == CONTAINER_SSH_AUTH_SOCK
    assert kwargs["labels"]["io.dbrennand.forge.command"] == "run"
    assert kwargs["security_opt"] == ["seccomp=unconfined", "apparmor=unconfined"]
    assert kwargs["environment"]["SSH_AUTH_SOCK"] == CONTAINER_SSH_AUTH_SOCK


def test_build_container_kwargs_keep_container(tmp_path: Path) -> None:
    """Disable Docker auto-removal when Forge keeps the container."""
    request = make_request(tmp_path, keep_container=True)
    kwargs = build_container_kwargs(request)
    assert kwargs["auto_remove"] is False


def test_build_container_kwargs_uses_generated_forge_container_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the Forge container naming convention for created containers."""
    request = make_request(tmp_path)
    monkeypatch.setattr("forge.docker_api.random.randrange", lambda upper_bound: 42)

    kwargs = build_container_kwargs(request)

    assert kwargs["name"] == "forge_000000000042"


def test_build_container_kwargs_sets_interactive_term_fallback(tmp_path: Path) -> None:
    """Default interactive sessions to a usable terminal type when missing."""
    request = make_request(tmp_path)
    request = ContainerRequest(
        command_name=request.command_name,
        image=request.image,
        workspace=request.workspace,
        keep_container=request.keep_container,
        extra_mounts=request.extra_mounts,
        forwarded_env={},
        command=request.command,
        interactive=True,
        host_codex_dir=request.host_codex_dir,
        host_codex_config_file=request.host_codex_config_file,
        host_gh_config_dir=request.host_gh_config_dir,
        host_ssh_auth_sock=request.host_ssh_auth_sock,
        host_uid=request.host_uid,
        host_gid=request.host_gid,
        nested_sandbox=request.nested_sandbox,
    )

    kwargs = build_container_kwargs(request)

    assert kwargs["environment"]["TERM"] == "xterm-256color"


def test_build_container_kwargs_omits_nested_sandbox_settings(tmp_path: Path) -> None:
    """Omit relaxed security options when nested sandboxing is disabled."""
    request = make_request(tmp_path)
    request = ContainerRequest(
        command_name=request.command_name,
        image=request.image,
        workspace=request.workspace,
        keep_container=request.keep_container,
        extra_mounts=request.extra_mounts,
        forwarded_env=request.forwarded_env,
        command=request.command,
        interactive=request.interactive,
        host_codex_dir=request.host_codex_dir,
        host_codex_config_file=None,
        host_gh_config_dir=request.host_gh_config_dir,
        host_ssh_auth_sock=None,
        host_uid=request.host_uid,
        host_gid=request.host_gid,
        nested_sandbox=False,
    )

    kwargs = build_container_kwargs(request)

    assert "security_opt" not in kwargs
    assert "SSH_AUTH_SOCK" not in kwargs["environment"]


def test_signal_to_docker_name() -> None:
    """Map forwarded host signals to Docker signal names."""
    assert signal_to_docker_name(signal.SIGINT) == "SIGINT"
    assert signal_to_docker_name(signal.SIGTERM) == "SIGTERM"
    assert signal_to_docker_name(signal.SIGHUP) == "SIGHUP"


def test_resize_terminal_uses_current_terminal_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resize the container using the current terminal dimensions."""
    runner = DockerRunner(client=object())
    observed: list[tuple[int, int]] = []

    class FakeContainer:
        """Capture terminal resize dimensions for assertions."""

        def resize(self, height: int, width: int) -> None:
            """Record requested resize dimensions."""
            observed.append((height, width))

    monkeypatch.setattr(
        "forge.docker_api.os.get_terminal_size",
        lambda fd: os.terminal_size((132, 43)),
    )

    runner._resize_terminal(FakeContainer(), 1)

    assert observed == [(43, 132)]


def test_terminal_size_uses_fallback_when_fd_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return the fallback terminal size when querying the fd fails."""

    def raise_os_error(fd: int) -> os.terminal_size:
        """Raise an OS error to simulate a missing TTY."""
        raise OSError("no tty")

    monkeypatch.setattr("forge.docker_api.os.get_terminal_size", raise_os_error)

    assert _terminal_size(1) == os.terminal_size((80, 24))


def test_signal_forwarder_uses_resize_callback_for_sigwinch() -> None:
    """Dispatch resize signals to the resize callback instead of Docker."""
    if not hasattr(signal, "SIGWINCH"):
        pytest.skip("SIGWINCH is not available on this platform")

    container = SimpleNamespace(kill=lambda signal: None)
    calls: list[str] = []
    forwarder = _SignalForwarder(container, on_resize=lambda: calls.append("resize"))

    forwarder._handler(signal.SIGWINCH, None)

    assert calls == ["resize"]


def test_raw_attached_socket_uses_underlying_socket() -> None:
    """Unwrap Docker socket attachments to their raw socket object."""
    raw_socket = object()
    attachment = SimpleNamespace(_sock=raw_socket)

    assert _raw_attached_socket(attachment) is raw_socket


def test_raw_attached_socket_accepts_socket_without_wrapper() -> None:
    """Accept already-raw sockets without modification."""
    raw_socket = object()

    assert _raw_attached_socket(raw_socket) is raw_socket


def test_close_attached_socket_closes_wrapper_response_before_attachment() -> None:
    """Close wrapper responses before closing the attachment itself."""
    events: list[str] = []

    class FakeAttachment:
        """Track attachment close ordering."""

        def __init__(self) -> None:
            """Initialize a fake attachment with a wrapper response slot."""
            self.closed = False
            self._sock = SimpleNamespace()
            self._response: object | None = None

        def close(self) -> None:
            """Record that the attachment was closed."""
            self.closed = True
            events.append("attachment.close")

    attachment = FakeAttachment()

    class FakeResponse:
        """Assert that response cleanup happens before attachment cleanup."""

        def close(self) -> None:
            """Record response cleanup while enforcing call order."""
            if attachment.closed:
                raise AssertionError("response closed after attachment")
            events.append("response.close")

    attachment._response = FakeResponse()

    _close_attached_socket(attachment)

    assert events == ["response.close", "attachment.close"]
    assert not hasattr(attachment, "_response")
    assert not hasattr(attachment._sock, "_response")


def test_close_attached_socket_closes_raw_socket_response_before_attachment() -> None:
    """Close raw-socket responses before closing the attachment wrapper."""
    events: list[str] = []

    class FakeAttachment:
        """Track close ordering for raw-socket response cleanup."""

        def __init__(self) -> None:
            """Initialize a fake attachment with a wrapped raw socket."""
            self.closed = False
            self._sock = SimpleNamespace()

        def close(self) -> None:
            """Record that the attachment was closed."""
            self.closed = True
            events.append("attachment.close")

    attachment = FakeAttachment()

    class FakeResponse:
        """Assert that raw-socket response cleanup happens before attachment cleanup."""

        def close(self) -> None:
            """Record response cleanup while enforcing call order."""
            if attachment.closed:
                raise AssertionError("response closed after attachment")
            events.append("response.close")

    attachment._sock._response = FakeResponse()

    _close_attached_socket(attachment)

    assert events == ["response.close", "attachment.close"]
    assert not hasattr(attachment._sock, "_response")


def test_wait_for_container_uses_cached_exit_code_after_auto_remove() -> None:
    """Use cached container state when wait loses the auto-removed container."""
    runner = DockerRunner(client=object())

    class FakeContainer:
        """Simulate an auto-removed container with cached state."""

        attrs: dict[str, dict[str, int]] = {"State": {"ExitCode": 0}}

        def wait(self) -> object:
            """Raise `NotFound` to emulate auto-removal after exit."""
            raise NotFound("missing")

    assert runner._wait_for_container(FakeContainer()) == 0


def test_wait_for_container_requires_cached_exit_code_when_missing() -> None:
    """Raise when auto-removed containers have no cached exit code."""
    runner = DockerRunner(client=object())

    class FakeContainer:
        """Simulate an auto-removed container without cached state."""

        attrs: dict[str, dict[str, int]] = {"State": {}}

        def wait(self) -> object:
            """Raise `NotFound` to emulate auto-removal after exit."""
            raise NotFound("missing")

    with pytest.raises(ContainerRuntimeError):
        runner._wait_for_container(FakeContainer())
