# Container Image

Forge publishes a default runtime image at `ghcr.io/dbrennand/forge:latest`.
This document describes the image build layout, the base image used in each stage,
and the tools that end up in the final runtime image.

## Base Image

All build stages currently start from `debian:bookworm-slim`.

This keeps the image family consistent across:

- the GitHub CLI download stage
- the `uv` download stage
- the `gitleaks` download stage
- the Codex CLI install stage
- the final runtime stage

## Build Stages

The image is built as a multi-stage Dockerfile.

### `gh-builder`

Purpose:
- Downloads and installs a pinned `gh` binary for the target architecture.

Base image:
- `debian:bookworm-slim`

Packages installed in this stage:
- `ca-certificates`
- `curl`
- `tar`

Artifacts produced:
- `/usr/local/bin/gh`

Notes:
- `TARGETARCH` is mapped to the upstream GitHub CLI archive naming.
- The downloaded archive is unpacked and only the `gh` binary is copied forward.

### `codex-builder`

Purpose:
- Installs the pinned Codex CLI with `npm`.

Base image:
- `debian:bookworm-slim`

Packages installed in this stage:
- `ca-certificates`
- `nodejs`
- `npm`

Artifacts produced:
- `/usr/local/bin/codex`
- `/usr/local/lib/node_modules`

Notes:
- Codex is installed globally as `@openai/codex@${CODEX_VERSION}`.
- The npm cache is cleaned before the stage completes.

### `uv-builder`

Purpose:
- Downloads and installs a pinned `uv` binary for the target architecture.

Base image:
- `debian:bookworm-slim`

Packages installed in this stage:
- `ca-certificates`
- `curl`
- `tar`

Artifacts produced:
- `/usr/local/bin/uv`
- `/usr/local/bin/uvx`

Notes:
- `TARGETARCH` is mapped to the upstream `uv` Linux GNU archive naming.
- Only the `uv` and `uvx` binaries are copied into the final image.

### `gitleaks-builder`

Purpose:
- Downloads and installs a pinned `gitleaks` binary for the target architecture.

Base image:
- `debian:bookworm-slim`

Packages installed in this stage:
- `ca-certificates`
- `curl`
- `tar`

Artifacts produced:
- `/usr/local/bin/gitleaks`

Notes:
- `TARGETARCH` is mapped to the upstream `gitleaks` Linux archive naming.
- Only the `gitleaks` binary is copied into the final image.

### Final Runtime Stage

Purpose:
- Provides the container environment used by `forge shell`, `forge codex`, and `forge run`.

Base image:
- `debian:bookworm-slim`

Packages installed directly in the final image:
- `bash`
- `bubblewrap`
- `ca-certificates`
- `curl`
- `git`
- `gosu`
- `nodejs`
- `openssh-client`
- `passwd`
- `ripgrep`
- `tini`

Artifacts copied from builder stages:
- `gh` from `gh-builder`
- `uv` and `uvx` from `uv-builder`
- `gitleaks` from `gitleaks-builder`
- global Node modules from `codex-builder`

The final stage then recreates the global `codex` launcher symlink:

- `/usr/local/bin/codex` -> `../lib/node_modules/@openai/codex/bin/codex.js`

This preserves the package-relative Node module context required by Codex's ESM
entrypoint.

The final stage also installs:

- `ai-guardian` with `uv tool install`

The AI Guardian installation uses:

- `UV_TOOL_BIN_DIR=/usr/local/bin`
- `UV_TOOL_DIR=/opt/uv/tools`
- `UV_PYTHON_INSTALL_DIR=/opt/uv/python`

This keeps the `ai-guardian` executable in the standard runtime `PATH` while
letting `uv` provision and retain the managed Python interpreter used by the
tool environment.

## Final Image Contents

The final runtime image includes these primary tools:

- Codex CLI `0.137.0`
- GitHub CLI `2.93.0`
- `uv` `0.11.21`
- AI Guardian `1.11.1`
- `gitleaks` `8.30.1`
- Node.js
- Git
- OpenSSH client
- `ripgrep`
- `curl`
- `bash`
- `tini`
- `gosu`
- `bubblewrap`

Operationally, the image also includes:

- the `forge` user and group, created with UID/GID `1000`
- `/usr/local/bin/forge-entrypoint`
- environment defaults for `HOME`, `XDG_CONFIG_HOME`, and `CODEX_HOME`
- `uv` tool and managed-Python directories under `/opt/uv`

## Entrypoint Behavior

The image entrypoint is `/usr/local/bin/forge-entrypoint`, wrapped by `tini`.

At container start, the entrypoint:

- requires `FORGE_HOST_UID` and `FORGE_HOST_GID`
- remaps the in-image `forge` account to match the invoking host user
- ensures `/home/forge`, `/home/forge/.config`, and AI Guardian config/state/cache
  directories exist
- starts the AI Guardian daemon in the background when the container command is
  `codex`, `codex exec`, or `/bin/bash`
- drops privileges with `gosu`

This is what allows Forge to run as a non-root user inside the container while
keeping file ownership aligned with the host workspace.

Although the installed `ai-guardian` package includes the `ai-guardian mcp-server`
subcommand, Forge does not register or start it for Codex. Codex uses AI Guardian
through hook configuration only.

## Architecture Support

The GitHub CLI install stage explicitly handles:

- `amd64`
- `arm64`

The release workflow publishes multi-architecture images for:

- `linux/amd64`
- `linux/arm64`

## Updating the Image

The pinned runtime tool versions are controlled from:

- `Dockerfile` for build arguments and installed packages
- `.github/workflows/release.yml` for the published build configuration

When the image contents change, update this document alongside the Dockerfile so
the documented final toolset and stage layout stay accurate.
