from __future__ import annotations

import platform
import stat
from collections.abc import Mapping
from pathlib import Path

from forge.config import (
    DEFAULT_IMAGE,
    FORWARDED_ENV_VARS,
    HOST_SERVICES_SSH_AUTH_SOCK,
    IMAGE_ENV_VAR,
)


def resolve_image(cli_image: str | None, environ: Mapping[str, str]) -> str:
    """Resolve the runtime image from CLI and environment inputs.

    Args:
        cli_image: Explicit image override from the CLI.
        environ: Environment mapping to inspect for fallback configuration.

    Returns:
        str: Docker image reference to use for the container.
    """
    if cli_image:
        return cli_image
    if IMAGE_ENV_VAR in environ and environ[IMAGE_ENV_VAR]:
        return environ[IMAGE_ENV_VAR]
    return DEFAULT_IMAGE


def collect_forwarded_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Collect whitelisted host environment variables for the container.

    Args:
        environ: Environment mapping to inspect.

    Returns:
        dict[str, str]: Forwarded environment variables with empty values omitted.
    """
    return {name: environ[name] for name in FORWARDED_ENV_VARS if environ.get(name)}


def resolve_ssh_auth_sock(
    environ: Mapping[str, str], *, host_platform: str | None = None
) -> Path | None:
    """Resolve a valid SSH agent mount source from the environment.

    Args:
        environ: Environment mapping to inspect.
        host_platform: Optional host platform override for tests.

    Returns:
        Path | None: Mount source path when available, otherwise `None`.
    """
    raw_path = environ.get("SSH_AUTH_SOCK")
    if not raw_path:
        return None

    candidate = Path(raw_path).expanduser().resolve()
    try:
        mode = candidate.stat().st_mode
    except OSError:
        return None

    if not stat.S_ISSOCK(mode):
        return None

    active_platform = platform.system() if host_platform is None else host_platform
    if active_platform == "Darwin":
        return Path(HOST_SERVICES_SSH_AUTH_SOCK)
    return candidate
