from __future__ import annotations

from pathlib import PurePosixPath

DEFAULT_IMAGE = "ghcr.io/dbrennand/forge:latest"
IMAGE_ENV_VAR = "FORGE_IMAGE"
FORGE_USER = "forge"
FORGE_HOME = "/home/forge"
CONTAINER_WORKSPACE = "/workspace"
CONTAINER_CODEX_HOME = f"{FORGE_HOME}/.codex"
CONTAINER_GH_CONFIG = f"{FORGE_HOME}/.config/gh"
FORWARDED_ENV_VARS = ("OPENAI_API_KEY", "GITHUB_TOKEN", "GH_TOKEN")
RESERVED_MOUNT_PATHS = (
    PurePosixPath(CONTAINER_WORKSPACE),
    PurePosixPath(CONTAINER_CODEX_HOME),
    PurePosixPath(CONTAINER_GH_CONFIG),
)
CONTAINER_LABELS = {
    "io.dbrennand.forge.managed": "true",
}
INTERACTIVE_TERMINATION_GRACE_SECONDS = 5
