# forge

`forge` is a Python CLI that launches Codex or a shell inside a prepared Docker runtime.

## Requirements

- Python 3.12+
- Docker
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

```bash
forge shell /path/to/repo
forge codex /path/to/repo
forge run --workspace /path/to/repo "explain this repository"
```

Additional mounts can be passed with repeated `--volume HOST:CTR[:ro|rw]`.

## Runtime image

The default runtime image is `ghcr.io/dbrennand/forge:latest`. It contains pinned versions of:

- Codex CLI `0.137.0`
- GitHub CLI `2.93.0`

## Development

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
bash scripts/smoke_runtime.sh forge:test
```

## Release

Create a version tag that matches `pyproject.toml`, for example `v0.1.0`. The release workflow publishes:

- `ghcr.io/dbrennand/forge:<version>`
- `ghcr.io/dbrennand/forge:latest`
