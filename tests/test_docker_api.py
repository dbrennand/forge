from __future__ import annotations

import io
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
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
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
        host_codex_hooks_file=hooks,
        host_gh_config_dir=gh,
        host_ssh_auth_sock=ssh_auth_sock,
        prepared_mount_dirs=(config.parent, hooks.parent),
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
    assert kwargs["environment"]["CODEX_HOME"] == "/home/forge/.codex/forge"
    assert kwargs["environment"]["FORGE_HOST_UID"] == "501"
    assert kwargs["volumes"][str(request.workspace)]["bind"] == "/workspace"
    assert kwargs["volumes"][str(request.host_codex_dir)]["bind"] == "/home/forge/.codex"
    assert str(request.host_codex_config_file) not in kwargs["volumes"]
    assert str(request.host_codex_hooks_file) not in kwargs["volumes"]
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
        host_codex_hooks_file=request.host_codex_hooks_file,
        host_gh_config_dir=request.host_gh_config_dir,
        host_ssh_auth_sock=request.host_ssh_auth_sock,
        prepared_mount_dirs=request.prepared_mount_dirs,
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
        host_codex_hooks_file=None,
        host_gh_config_dir=request.host_gh_config_dir,
        host_ssh_auth_sock=None,
        prepared_mount_dirs=(),
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


def test_run_streaming_replays_existing_stdout_and_stderr() -> None:
    """Forward non-interactive output already present when Forge starts reading logs."""
    stdout = io.BytesIO()
    stderr = io.BytesIO()
    runner = DockerRunner(client=object(), stdout=stdout, stderr=stderr)
    observed_kwargs: dict[str, object] = {}

    class FakeContainer:
        """Capture log streaming arguments while returning demuxed output."""

        def attach(self, **kwargs: object) -> list[tuple[bytes | None, bytes | None]]:
            """Return output that may have been emitted before log streaming began."""
            observed_kwargs.update(kwargs)
            return [(b"out\n", None), (None, b"err\n")]

        def wait(self) -> dict[str, int]:
            """Report successful container exit."""
            return {"StatusCode": 0}

    assert runner._run_streaming(FakeContainer()) == 0
    assert observed_kwargs == {
        "stream": True,
        "stdout": True,
        "stderr": True,
        "logs": True,
        "demux": True,
    }
    assert stdout.getvalue() == b"out\n"
    assert stderr.getvalue() == b"err\n"


def test_run_interactive_drains_socket_output_after_container_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write pending interactive output even when Docker already reports exit."""
    writes: list[bytes] = []

    class FakeSocket:
        """Socket-like object with one pending output chunk."""

        def __init__(self) -> None:
            """Initialize the socket with pending output."""
            self.recv_calls = 0

        def setblocking(self, value: bool) -> None:
            """Accept nonblocking mode changes."""

        def recv(self, size: int) -> bytes:
            """Return one pending output chunk."""
            self.recv_calls += 1
            return b"trailing output"

        def sendall(self, data: bytes) -> None:
            """Accept stdin writes."""

    class FakeAttachment:
        """Docker socket attachment wrapper."""

        def __init__(self) -> None:
            """Initialize the wrapped socket."""
            self._sock = FakeSocket()
            self.closed = False

        def close(self) -> None:
            """Record that the attachment was closed."""
            self.closed = True

    class FakeContainer:
        """Interactive container whose socket has pending output after exit."""

        attrs: dict[str, dict[str, int]] = {"State": {"ExitCode": 0}}

        def __init__(self) -> None:
            """Initialize the fake container."""
            self.attachment = FakeAttachment()

        def attach_socket(self, params: dict[str, int]) -> FakeAttachment:
            """Return the fake Docker attachment."""
            return self.attachment

        def resize(self, height: int, width: int) -> None:
            """Accept terminal resize requests."""

        def wait(self) -> dict[str, int]:
            """Report successful container exit."""
            return {"StatusCode": 0}

    class FakeSelector:
        """Selector that reports pending socket output once."""

        def __init__(self) -> None:
            """Initialize selector state."""
            self.socket_key: SimpleNamespace | None = None
            self.select_calls = 0

        def register(self, fileobj: object, events: int, data: str) -> None:
            """Capture selector registrations."""
            if data == "socket":
                self.socket_key = SimpleNamespace(data=data)

        def unregister(self, fileobj: object) -> None:
            """Accept unregister calls."""

        def select(self, timeout: float) -> list[tuple[SimpleNamespace, None]]:
            """Return one socket event before becoming idle."""
            self.select_calls += 1
            if self.select_calls == 1:
                assert self.socket_key is not None
                return [(self.socket_key, None)]
            return []

        def close(self) -> None:
            """Accept selector cleanup."""

    class ExitAwareRunner(DockerRunner):
        """Runner that reports the container as already exited."""

        def _container_exited(self, container: object) -> bool:
            """Report that Docker already marked the container exited."""
            return True

    monkeypatch.setattr("forge.docker_api.selectors.DefaultSelector", FakeSelector)
    monkeypatch.setattr("forge.docker_api.sys.stdin", SimpleNamespace(fileno=lambda: 10))
    monkeypatch.setattr("forge.docker_api.sys.stdout", SimpleNamespace(fileno=lambda: 11))
    monkeypatch.setattr("forge.docker_api.termios.tcgetattr", lambda fd: ["raw"])
    monkeypatch.setattr("forge.docker_api.termios.tcsetattr", lambda fd, when, attrs: None)
    monkeypatch.setattr("forge.docker_api.tty.setraw", lambda fd: None)
    monkeypatch.setattr("forge.docker_api.os.write", lambda fd, data: writes.append(data))

    runner = ExitAwareRunner(client=object())

    assert runner._run_interactive(FakeContainer()) == 0
    assert writes == [b"trailing output"]


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


def test_execute_cleans_up_prepared_mount_dirs(tmp_path: Path) -> None:
    """Remove prepared temporary mount directories after container execution."""
    request = make_request(tmp_path)
    observed: list[Path] = []

    class FakeContainer:
        """Simulate a successful non-interactive container run."""

        id = "container-id"

        def start(self) -> None:
            """Start the fake container."""

        def attach(self, **kwargs: object) -> list[tuple[bytes | None, bytes | None]]:
            """Return no streamed output."""
            return []

        def wait(self) -> dict[str, int]:
            """Report successful container exit."""
            return {"StatusCode": 0}

    class FakeContainers:
        """Expose the Docker `containers.create` surface used by the runner."""

        def create(self, **kwargs: object) -> FakeContainer:
            """Create the fake container."""
            return FakeContainer()

    class CleanupTrackingRunner(DockerRunner):
        """Record prepared mount cleanup without touching the filesystem."""

        def _cleanup_prepared_mount_dirs(self, request: ContainerRequest) -> None:
            """Capture the directories that would be cleaned."""
            observed.extend(request.prepared_mount_dirs)

    client = SimpleNamespace(containers=FakeContainers())
    runner = CleanupTrackingRunner(client=client)

    assert runner.execute(request) == 0
    assert observed == list(request.prepared_mount_dirs)
