from __future__ import annotations

import sys
from typing import BinaryIO


def write_stdout(data: bytes, *, stream: BinaryIO = sys.stdout.buffer) -> None:
    stream.write(data)
    stream.flush()


def write_stderr(data: bytes, *, stream: BinaryIO = sys.stderr.buffer) -> None:
    stream.write(data)
    stream.flush()


def print_kept_container_id(container_id: str) -> None:
    sys.stderr.write(f"Kept container: {container_id}\n")
    sys.stderr.flush()
