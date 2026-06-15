from __future__ import annotations

from pathlib import PurePosixPath

DEFAULT_IMAGE = "ghcr.io/dbrennand/forge:latest"
IMAGE_ENV_VAR = "FORGE_IMAGE"
FORGE_USER = "forge"
FORGE_HOME = "/home/forge"
CONTAINER_WORKSPACE = "/workspace"
CONTAINER_CODEX_HOME = f"{FORGE_HOME}/.codex"
CONTAINER_GH_CONFIG = f"{FORGE_HOME}/.config/gh"
CONTAINER_SSH_AUTH_SOCK = "/tmp/forge-ssh-auth.sock"
HOST_SERVICES_SSH_AUTH_SOCK = "/run/host-services/ssh-auth.sock"
FORWARDED_ENV_VARS = (
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "TERM",
    "COLORTERM",
    "LANG",
    "LC_ALL",
)
RESERVED_MOUNT_PATHS = (
    PurePosixPath(CONTAINER_WORKSPACE),
    PurePosixPath(CONTAINER_CODEX_HOME),
    PurePosixPath(CONTAINER_GH_CONFIG),
    PurePosixPath(CONTAINER_SSH_AUTH_SOCK),
)
CONTAINER_LABELS = {
    "io.dbrennand.forge.managed": "true",
}
INTERACTIVE_TERMINATION_GRACE_SECONDS = 5
