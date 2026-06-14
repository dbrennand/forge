from __future__ import annotations

import sys
from typing import BinaryIO


def write_stdout(data: bytes, *, stream: BinaryIO = sys.stdout.buffer) -> None:
    """Write binary data to stdout and flush immediately.

    Args:
        data: Bytes to write.
        stream: Output stream override, primarily for tests.
    """
    stream.write(data)
    stream.flush()


def write_stderr(data: bytes, *, stream: BinaryIO = sys.stderr.buffer) -> None:
    """Write binary data to stderr and flush immediately.

    Args:
        data: Bytes to write.
        stream: Output stream override, primarily for tests.
    """
    stream.write(data)
    stream.flush()


def print_kept_container_id(container_id: str) -> None:
    """Print the identifier of a container that Forge intentionally preserved.

    Args:
        container_id: Docker container identifier.
    """
    sys.stderr.write(f"Kept container: {container_id}\n")
    sys.stderr.flush()
