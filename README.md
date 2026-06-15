# forge

`forge` is a Python CLI that launches Codex or a shell inside a prepared Docker-compatible container runtime.

## Requirements

- Python 3.12+
- A Docker-compatible container runtime such as Docker or OrbStack
- `~/.codex/auth.json`
- `$HOME/.config/gh/`

## Install

```bash
uv tool install .
```

For local development:

```bash
uv run forge --help
```

## Commands

Forge provides `shell`, `codex`, and `run` commands.
See [docs/commands.md](/Users/dab/github.com/dbrennand/forge/docs/commands.md) for command purposes, options, examples, and SSH agent mounting behavior.

## Runtime image

The default runtime image is `ghcr.io/dbrennand/forge:latest`.
See [docs/container-image.md](/Users/dab/github.com/dbrennand/forge/docs/container-image.md) for details on the base image, build stages, pinned tool versions, and the tools included in the final runtime image.

## Development

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
bash scripts/smoke_runtime.sh forge:test
```

`uv run pytest` prints a terminal coverage summary by default. For an HTML report, run:

```bash
uv run pytest --cov-report=html
```

In GitHub Actions, the CI workflow also appends the coverage table to the job summary.

## Release

Create a version tag that matches `pyproject.toml`, for example `0.1.0`. The release workflow publishes:

- `ghcr.io/dbrennand/forge:<version>`
- `ghcr.io/dbrennand/forge:latest`
