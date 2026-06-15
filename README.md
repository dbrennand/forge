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

When Forge is launched from a host session with an active SSH agent, it automatically mounts
that agent into the container and exposes it to in-container tools such as `git`. On macOS
hosts, Forge uses the container runtime's host-services SSH socket instead of bind-mounting
the raw host agent socket path.

## Runtime image

The default runtime image is `ghcr.io/dbrennand/forge:latest`. It contains pinned versions of:

- Codex CLI `0.137.0`
- GitHub CLI `2.93.0`
- `ripgrep` for fast in-container code search
- Debian `bubblewrap` so Codex can use the host-provided sandbox helper instead of its bundled fallback

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

Create a version tag that matches `pyproject.toml`, for example `v0.1.0`. The release workflow publishes:

- `ghcr.io/dbrennand/forge:<version>`
- `ghcr.io/dbrennand/forge:latest`
