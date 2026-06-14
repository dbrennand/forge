# forge

`forge` is a Python CLI that launches Codex or a shell inside a prepared Docker runtime.

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
forge shell --workspace /path/to/repo
forge codex --workspace /path/to/repo
forge run --workspace /path/to/repo "explain this repository"
```

## Development

```bash
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

