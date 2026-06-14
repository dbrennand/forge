from __future__ import annotations

from collections.abc import Mapping

from forge.config import DEFAULT_IMAGE, FORWARDED_ENV_VARS, IMAGE_ENV_VAR


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
