from __future__ import annotations

from collections.abc import Mapping

from forge.config import DEFAULT_IMAGE, FORWARDED_ENV_VARS, IMAGE_ENV_VAR


def resolve_image(cli_image: str | None, environ: Mapping[str, str]) -> str:
    if cli_image:
        return cli_image
    if IMAGE_ENV_VAR in environ and environ[IMAGE_ENV_VAR]:
        return environ[IMAGE_ENV_VAR]
    return DEFAULT_IMAGE


def collect_forwarded_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {name: environ[name] for name in FORWARDED_ENV_VARS if environ.get(name)}
