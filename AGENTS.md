# Repository Guidelines

## Project Structure & Module Organization

Forge is a Python CLI packaged from `src/forge/`. Keep command-line parsing in `src/forge/args.py`, top-level orchestration in `src/forge/cli.py`, Docker interactions in `src/forge/docker_api.py`, and focused helpers in modules such as `validation.py`, `mounts.py`, `commands.py`, and `env.py`. Tests live in `tests/` and mirror the production modules with files like `tests/test_args.py` and `tests/test_docker_api.py`. Container runtime assets are kept in `Dockerfile` and `docker/entrypoint.sh`. Use `scripts/smoke_runtime.sh` for the Docker-backed smoke check.

## Build, Test, and Development Commands

- `uv sync --group dev --frozen` installs locked development dependencies.
- `uv run forge --help` checks the CLI entrypoint locally.
- `uv run pytest` runs the full unit test suite.
- `uv run ruff check` runs lint rules.
- `uv run ruff format --check` verifies formatting.
- `uv run mypy` runs strict type checking.
- `bash scripts/smoke_runtime.sh forge:test` validates the built runtime image after `docker build -t forge:test .`.

## Coding Style & Naming Conventions

Target Python 3.12+ and keep code fully typed. Ruff enforces import ordering and core lint rules; mypy runs in `strict` mode, so avoid untyped defs in `src/forge`. Use 4-space indentation, snake_case for modules/functions, and dataclass names in PascalCase. Keep functions narrow and place CLI-facing errors behind typed exceptions in `errors.py`.

## Testing Guidelines

Use `pytest` for all tests. Add or update tests whenever CLI behavior, validation, container spec generation, or runtime command assembly changes. Name files `test_<module>.py` and test functions `test_<behavior>()`. Prefer focused unit tests first, then extend the smoke path only when Docker/runtime behavior changes.

## Commit & Pull Request Guidelines

Use small, reviewable commits with Conventional Commit prefixes such as `feat:`, `fix:`, `ci:`, `test:`, and `build:`. Sign commits before pushing. Pull requests should describe the user-visible behavior change, note any Docker or CI impact, and list exact verification commands you ran.

## Security & Configuration Tips

Do not commit real credentials from `~/.codex` or GitHub auth state. Keep host-path assumptions explicit, and preserve the contract that Forge diagnostics go to stderr while `forge run` passes child stdout/stderr through unchanged.
