# Repository Guidelines

## Project Structure & Module Organization

Forge is a Python CLI packaged from `src/forge/`. Keep command-line parsing in `src/forge/args.py`, top-level orchestration in `src/forge/cli.py`, Docker interactions in `src/forge/docker_api.py`, and focused helpers in modules such as `validation.py`, `mounts.py`, `commands.py`, and `env.py`. Tests live in `tests/` and mirror the production modules with files like `tests/test_args.py` and `tests/test_docker_api.py`. Container runtime assets are kept in `Dockerfile` and `docker/entrypoint.sh`. Repository documentation lives in `docs/`, including `docs/commands.md` for CLI command reference material and `docs/container-image.md` for runtime image internals. Use `scripts/smoke_runtime.sh` for the Docker-backed smoke check.

## Build, Test, and Development Commands

- `uv sync --group dev --frozen` installs locked development dependencies.
- `uv run forge --help` checks the CLI entrypoint locally.
- `uv run pytest` runs the full unit test suite.
- `uv run ruff check` runs lint rules.
- `uv run ruff format --check` verifies formatting.
- `uv run mypy` runs strict type checking.
- `bash scripts/smoke_runtime.sh forge:test` validates the built runtime image after `docker build -t forge:test .`.

## Coding Style & Naming Conventions

Target Python 3.12+ and keep code fully typed. Ruff enforces import ordering and core lint rules; mypy runs in `strict` mode, so avoid untyped defs in `src/forge`. Use 4-space indentation, snake_case for modules/functions, and dataclass names in PascalCase. Add Google-style docstrings to every class and function in the repo, including tests; use sections such as `Args`, `Returns`, `Raises`, and `Attributes` when they add signal. Keep functions narrow and place CLI-facing errors behind typed exceptions in `errors.py`.

## Testing Guidelines

Use `pytest` for all tests. Add or update tests whenever CLI behavior, validation, container spec generation, or runtime command assembly changes. Name files `test_<module>.py` and test functions `test_<behavior>()`. Prefer focused unit tests first, then extend the smoke path only when Docker/runtime behavior changes.

## Documentation Guidelines

Keep `README.md` concise and link to focused docs in `docs/` for detailed operational reference.

- Update `docs/commands.md` when changing command purpose, CLI options, examples, mount behavior, SSH agent behavior, image selection, or other user-facing command semantics.
- Update `docs/container-image.md` when changing the Dockerfile, build stages, base image choice, published architectures, pinned tool versions, entrypoint behavior, or the set of tools included in the final runtime image.
- When moving detail out of `README.md`, leave a short summary there and link to the dedicated document with relative Markdown links.

## Commit & Pull Request Guidelines

Use small, reviewable commits with Conventional Commit prefixes such as `feat:`, `fix:`, `ci:`, `test:`, and `build:`. Sign commits before pushing. Pull requests should describe the user-visible behavior change, note any Docker or CI impact, and list exact verification commands you ran.

## Security & Configuration Tips

Do not commit real credentials from `~/.codex` or GitHub auth state. Keep host-path assumptions explicit, and preserve the contract that Forge diagnostics go to stderr while `forge run` passes child stdout/stderr through unchanged.
