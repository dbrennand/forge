from __future__ import annotations

import os
import selectors
import signal
import socket
import sys
import termios
import threading
import tty
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, BinaryIO

import docker
from docker.errors import DockerException, NotFound

from forge.config import (
    CONTAINER_CODEX_HOME,
    CONTAINER_GH_CONFIG,
    CONTAINER_LABELS,
    CONTAINER_WORKSPACE,
    FORGE_HOME,
    INTERACTIVE_TERMINATION_GRACE_SECONDS,
)
from forge.errors import ContainerRuntimeError, DockerUnavailableError
from forge.models import ContainerRequest, VolumeMount
from forge.output import print_kept_container_id, write_stderr, write_stdout

FORWARDED_SIGNALS = {
    signal.SIGINT: "SIGINT",
    signal.SIGTERM: "SIGTERM",
    signal.SIGHUP: "SIGHUP",
}


def build_container_kwargs(request: ContainerRequest) -> dict[str, Any]:
    """Translate a container request into Docker SDK keyword arguments.

    Args:
        request: Fully resolved Forge container request.

    Returns:
        dict[str, Any]: Keyword arguments accepted by `containers.create`.
    """
    volumes = {
        str(request.workspace): {"bind": CONTAINER_WORKSPACE, "mode": "rw"},
        str(request.host_codex_dir): {"bind": CONTAINER_CODEX_HOME, "mode": "rw"},
        str(request.host_gh_config_dir): {"bind": CONTAINER_GH_CONFIG, "mode": "ro"},
    }
    if request.host_codex_config_file is not None:
        volumes[str(request.host_codex_config_file)] = {
            "bind": f"{CONTAINER_CODEX_HOME}/config.toml",
            "mode": "ro",
        }
    volumes.update(_volume_mapping(request.extra_mounts))

    environment = {
        "HOME": FORGE_HOME,
        "XDG_CONFIG_HOME": f"{FORGE_HOME}/.config",
        "CODEX_HOME": CONTAINER_CODEX_HOME,
        "PYTHONUNBUFFERED": "1",
        "FORGE_HOST_UID": str(request.host_uid),
        "FORGE_HOST_GID": str(request.host_gid),
        **request.forwarded_env,
    }
    if request.interactive and environment.get("TERM") in {None, "", "dumb"}:
        environment["TERM"] = "xterm-256color"

    labels = dict(CONTAINER_LABELS)
    labels["io.dbrennand.forge.command"] = request.command_name

    kwargs = {
        "image": request.image,
        "command": list(request.command),
        "detach": True,
        "auto_remove": request.auto_remove,
        "stdin_open": request.interactive,
        "tty": request.interactive,
        "working_dir": CONTAINER_WORKSPACE,
        "volumes": volumes,
        "environment": environment,
        "labels": labels,
        "user": "0:0",
    }
    if request.nested_sandbox:
        kwargs["security_opt"] = ["seccomp=unconfined", "apparmor=unconfined"]
    return kwargs


def signal_to_docker_name(signum: int) -> str | None:
    """Map a host signal number to the Docker signal name to forward.

    Args:
        signum: Numeric host signal.

    Returns:
        str | None: Docker signal name, or `None` when the signal is not forwarded.
    """
    return FORWARDED_SIGNALS.get(signal.Signals(signum))


@dataclass
class DockerRunner:
    """Execute Forge container requests through the Docker SDK.

    Attributes:
        client: Docker SDK client instance.
        stdout: Stream used for forwarded container stdout.
        stderr: Stream used for forwarded container stderr.
    """

    client: Any
    stdout: BinaryIO = sys.stdout.buffer
    stderr: BinaryIO = sys.stderr.buffer

    @classmethod
    def from_env(cls) -> DockerRunner:
        """Create a Docker runner using environment-based Docker discovery.

        Returns:
            DockerRunner: Runner backed by `docker.from_env()`.
        """
        return cls(client=docker.from_env())  # type: ignore[attr-defined]

    def ping(self) -> None:
        """Verify that the Docker daemon is reachable.

        Raises:
            DockerUnavailableError: If the Docker daemon cannot be contacted.
        """
        try:
            self.client.ping()
        except DockerException as exc:
            raise DockerUnavailableError("Docker daemon is unavailable") from exc

    def execute(self, request: ContainerRequest) -> int:
        """Create, start, and monitor the requested container.

        Args:
            request: Fully resolved Forge container request.

        Returns:
            int: Container exit status.

        Raises:
            ContainerRuntimeError: If Docker fails while creating or running the container.
        """
        container = None
        started = False
        try:
            container = self.client.containers.create(**build_container_kwargs(request))
            container.start()
            started = True
            if request.interactive:
                return self._run_interactive(container)
            return self._run_streaming(container)
        except DockerException as exc:
            raise ContainerRuntimeError(f"Docker operation failed: {exc}") from exc
        finally:
            if request.keep_container and container is not None:
                print_kept_container_id(container.id)
            elif container is not None and not started:
                with suppress(DockerException):
                    container.remove(force=True)

    def _run_streaming(self, container: Any) -> int:
        """Stream non-interactive container output until completion.

        Args:
            container: Docker SDK container object.

        Returns:
            int: Container exit status.

        Raises:
            ContainerRuntimeError: If output streaming fails.
        """
        stream_error: list[BaseException] = []

        def _pump() -> None:
            """Pump attached container output into Forge stdio streams."""
            try:
                for stdout_chunk, stderr_chunk in container.attach(
                    stream=True,
                    stdout=True,
                    stderr=True,
                    demux=True,
                ):
                    if stdout_chunk:
                        write_stdout(stdout_chunk, stream=self.stdout)
                    if stderr_chunk:
                        write_stderr(stderr_chunk, stream=self.stderr)
            except BaseException as exc:  # pragma: no cover
                stream_error.append(exc)

        thread = threading.Thread(target=_pump, daemon=True)
        thread.start()

        with _SignalForwarder(container):
            result = container.wait()

        thread.join()
        if stream_error:
            raise ContainerRuntimeError(f"Streaming container output failed: {stream_error[0]}")
        return int(result["StatusCode"])

    def _run_interactive(self, container: Any) -> int:
        """Run an interactive container session attached to the current TTY.

        Args:
            container: Docker SDK container object.

        Returns:
            int: Container exit status.

        Raises:
            ContainerRuntimeError: If the interactive attach disconnects unexpectedly or
                terminal resize operations fail.
        """
        socket_attachment = container.attach_socket(
            params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1}
        )
        attached_socket = _raw_attached_socket(socket_attachment)
        attached_socket.setblocking(False)

        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()
        self._resize_terminal(container, stdout_fd)
        selector = selectors.DefaultSelector()
        selector.register(attached_socket, selectors.EVENT_READ, "socket")
        selector.register(stdin_fd, selectors.EVENT_READ, "stdin")
        previous_termios = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

        with _SignalForwarder(
            container,
            on_resize=lambda: self._resize_terminal(container, stdout_fd),
        ):
            try:
                while True:
                    if self._container_exited(container):
                        break
                    events = selector.select(timeout=0.1)
                    if not events:
                        continue
                    for key, _ in events:
                        if key.data == "stdin":
                            try:
                                data = os.read(stdin_fd, 1024)
                            except OSError:
                                data = b""
                            if not data:
                                selector.unregister(stdin_fd)
                                with suppress(OSError):
                                    attached_socket.shutdown(socket.SHUT_WR)
                                continue
                            attached_socket.sendall(data)
                        else:
                            try:
                                data = attached_socket.recv(4096)
                            except BlockingIOError:
                                continue
                            if not data:
                                if self._container_running(container):
                                    self._force_stop(container)
                                    raise ContainerRuntimeError(
                                        "Interactive attach disconnected while "
                                        "the container was still running"
                                    )
                                break
                            os.write(stdout_fd, data)
                    else:
                        continue
                    break
            finally:
                selector.close()
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, previous_termios)
                _close_attached_socket(socket_attachment)

        return self._wait_for_container(container)

    def _force_stop(self, container: Any) -> None:
        """Terminate a still-running interactive container.

        Args:
            container: Docker SDK container object.
        """
        container.kill(signal="SIGTERM")
        try:
            container.wait(timeout=INTERACTIVE_TERMINATION_GRACE_SECONDS)
        except DockerException:
            container.kill(signal="SIGKILL")

    def _resize_terminal(self, container: Any, fd: int) -> None:
        """Resize the container TTY to match the current host terminal.

        Args:
            container: Docker SDK container object.
            fd: File descriptor used to query terminal size.

        Raises:
            ContainerRuntimeError: If Docker rejects the resize request.
        """
        size = _terminal_size(fd)
        try:
            container.resize(height=size.lines, width=size.columns)
        except DockerException as exc:
            raise ContainerRuntimeError(f"Failed to resize interactive terminal: {exc}") from exc

    def _container_exited(self, container: Any) -> bool:
        """Check whether a container has already exited.

        Args:
            container: Docker SDK container object.

        Returns:
            bool: `True` when the container is no longer running.
        """
        try:
            container.reload()
        except NotFound:
            return True
        return bool(container.status in {"exited", "dead", "removing"})

    def _container_running(self, container: Any) -> bool:
        """Check whether a container is currently running.

        Args:
            container: Docker SDK container object.

        Returns:
            bool: `True` when the container status is `running`.
        """
        try:
            container.reload()
        except NotFound:
            return False
        return bool(container.status == "running")

    def _wait_for_container(self, container: Any) -> int:
        """Wait for a container to exit, tolerating auto-removal races.

        Args:
            container: Docker SDK container object.

        Returns:
            int: Container exit status.
        """
        try:
            result = container.wait()
        except NotFound:
            return self._cached_exit_code(container)
        return int(result["StatusCode"])

    def _cached_exit_code(self, container: Any) -> int:
        """Read a container exit code from cached attributes.

        Args:
            container: Docker SDK container object.

        Returns:
            int: Cached container exit status.

        Raises:
            ContainerRuntimeError: If no cached exit status is available.
        """
        exit_code = container.attrs.get("State", {}).get("ExitCode")
        if isinstance(exit_code, int):
            return exit_code
        raise ContainerRuntimeError("Container exited before Forge could determine its exit status")


class _SignalForwarder:
    """Temporarily forward host signals to a running Docker container."""

    def __init__(self, container: Any, *, on_resize: Callable[[], None] | None = None) -> None:
        """Initialize a signal forwarder for the provided container.

        Args:
            container: Docker SDK container object.
            on_resize: Optional callback invoked for terminal resize signals.
        """
        self._container = container
        self._on_resize = on_resize
        self._previous_handlers: dict[signal.Signals, Any] = {}

    def __enter__(self) -> _SignalForwarder:
        """Install temporary signal handlers for the managed container.

        Returns:
            _SignalForwarder: The active context manager instance.
        """
        for signum in FORWARDED_SIGNALS:
            self._previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handler)
        if hasattr(signal, "SIGWINCH") and self._on_resize is not None:
            self._previous_handlers[signal.SIGWINCH] = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._handler)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Restore the previous process signal handlers.

        Args:
            exc_type: Exception type raised inside the context, if any.
            exc: Exception instance raised inside the context, if any.
            tb: Traceback raised inside the context, if any.
        """
        for signum, previous in self._previous_handlers.items():
            signal.signal(signum, previous)

    def _handler(self, signum: int, _frame: object) -> None:
        """Handle a forwarded host signal.

        Args:
            signum: Numeric host signal.
            _frame: Ignored current stack frame from the signal handler API.
        """
        is_resize_signal = hasattr(signal, "SIGWINCH") and signum == signal.SIGWINCH
        if self._on_resize is not None and is_resize_signal:
            self._on_resize()
            return
        docker_signal = signal_to_docker_name(signum)
        if docker_signal is None:
            return
        with suppress(DockerException):
            self._container.kill(signal=docker_signal)


def _volume_mapping(mounts: tuple[VolumeMount, ...]) -> dict[str, dict[str, str]]:
    """Convert validated mounts into Docker SDK volume mapping format.

    Args:
        mounts: Validated extra bind mounts.

    Returns:
        dict[str, dict[str, str]]: Docker-compatible volume mapping.
    """
    return {
        str(mount.host_path): {"bind": mount.container_path.as_posix(), "mode": mount.mode}
        for mount in mounts
    }


def _raw_attached_socket(socket_attachment: Any) -> Any:
    """Extract the raw socket from a Docker socket wrapper when present.

    Args:
        socket_attachment: Docker SDK socket wrapper or raw socket object.

    Returns:
        Any: Raw socket-like object used for I/O.
    """
    return getattr(socket_attachment, "_sock", socket_attachment)


def _close_attached_socket(socket_attachment: Any) -> None:
    """Close Docker attach resources in an order that preserves buffered responses.

    Args:
        socket_attachment: Docker SDK socket wrapper or raw socket object.
    """
    for response_owner in (socket_attachment, _raw_attached_socket(socket_attachment)):
        response = getattr(response_owner, "_response", None)
        if response is None:
            continue
        response.close()
        with suppress(AttributeError):
            del response_owner._response
    socket_attachment.close()


def _terminal_size(fd: int) -> os.terminal_size:
    """Read terminal size with a stable fallback for non-TTY environments.

    Args:
        fd: File descriptor used to inspect terminal geometry.

    Returns:
        os.terminal_size: Terminal size, or an 80x24 fallback when unavailable.
    """
    try:
        return os.get_terminal_size(fd)
    except OSError:
        return os.terminal_size((80, 24))
