from __future__ import annotations

import os
import selectors
import signal
import socket
import sys
import termios
import threading
import tty
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, BinaryIO

import docker
from docker.errors import DockerException

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
    volumes = {
        str(request.workspace): {"bind": CONTAINER_WORKSPACE, "mode": "rw"},
        str(request.host_codex_dir): {"bind": CONTAINER_CODEX_HOME, "mode": "rw"},
        str(request.host_gh_config_dir): {"bind": CONTAINER_GH_CONFIG, "mode": "ro"},
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

    labels = dict(CONTAINER_LABELS)
    labels["io.dbrennand.forge.command"] = request.command_name

    return {
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


def signal_to_docker_name(signum: int) -> str | None:
    return FORWARDED_SIGNALS.get(signal.Signals(signum))


@dataclass
class DockerRunner:
    client: Any
    stdout: BinaryIO = sys.stdout.buffer
    stderr: BinaryIO = sys.stderr.buffer

    @classmethod
    def from_env(cls) -> DockerRunner:
        return cls(client=docker.from_env())

    def ping(self) -> None:
        try:
            self.client.ping()
        except DockerException as exc:
            raise DockerUnavailableError("Docker daemon is unavailable") from exc

    def execute(self, request: ContainerRequest) -> int:
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
        stream_error: list[BaseException] = []

        def _pump() -> None:
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
        socket_wrapper = container.attach_socket(
            params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1}
        )
        attached_socket = socket_wrapper._sock
        attached_socket.setblocking(False)

        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()
        selector = selectors.DefaultSelector()
        selector.register(attached_socket, selectors.EVENT_READ, "socket")
        selector.register(stdin_fd, selectors.EVENT_READ, "stdin")
        previous_termios = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

        with _SignalForwarder(container):
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
                socket_wrapper.close()

        result = container.wait()
        return int(result["StatusCode"])

    def _force_stop(self, container: Any) -> None:
        container.kill(signal="SIGTERM")
        try:
            container.wait(timeout=INTERACTIVE_TERMINATION_GRACE_SECONDS)
        except DockerException:
            container.kill(signal="SIGKILL")

    def _container_exited(self, container: Any) -> bool:
        container.reload()
        return bool(container.status in {"exited", "dead", "removing"})

    def _container_running(self, container: Any) -> bool:
        container.reload()
        return bool(container.status == "running")


class _SignalForwarder:
    def __init__(self, container: Any) -> None:
        self._container = container
        self._previous_handlers: dict[signal.Signals, Any] = {}

    def __enter__(self) -> _SignalForwarder:
        for signum in FORWARDED_SIGNALS:
            self._previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handler)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        for signum, previous in self._previous_handlers.items():
            signal.signal(signum, previous)

    def _handler(self, signum: int, _frame: object) -> None:
        docker_signal = signal_to_docker_name(signum)
        if docker_signal is None:
            return
        with suppress(DockerException):
            self._container.kill(signal=docker_signal)


def _volume_mapping(mounts: tuple[VolumeMount, ...]) -> dict[str, dict[str, str]]:
    return {
        str(mount.host_path): {"bind": mount.container_path.as_posix(), "mode": mount.mode}
        for mount in mounts
    }
