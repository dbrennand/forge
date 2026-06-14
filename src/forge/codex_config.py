from __future__ import annotations

import tempfile
from pathlib import Path


def prepare_container_config(codex_home: Path) -> Path | None:
    """Prepare a sanitized Codex config file for mounting into the container.

    Args:
        codex_home: Host Codex home directory.

    Returns:
        Path | None: Path to a temporary sanitized config file, or `None` when no
        host config exists.
    """
    config_path = codex_home / "config.toml"
    if not config_path.is_file():
        return None

    sanitized = sanitize_config(config_path.read_text(encoding="utf-8"))
    temp_dir = Path(tempfile.mkdtemp(prefix="forge-codex-config-"))
    prepared_config = temp_dir / "config.toml"
    prepared_config.write_text(sanitized, encoding="utf-8")
    return prepared_config


def sanitize_config(content: str) -> str:
    """Remove host-only Codex config settings before mounting into the container.

    Args:
        content: Raw `config.toml` contents from the host.

    Returns:
        str: Sanitized config contents safe for the container runtime.
    """
    sanitized_blocks: list[str] = []
    for header, block in _iter_config_blocks(content):
        if header is None:
            sanitized_blocks.append(_strip_top_level_notify(block))
            continue
        if _is_skipped_section(header):
            continue
        sanitized_blocks.append(block)
    return "".join(sanitized_blocks)


def _iter_config_blocks(content: str) -> list[tuple[str | None, str]]:
    """Split TOML content into top-level blocks keyed by section header.

    Args:
        content: Raw TOML content.

    Returns:
        list[tuple[str | None, str]]: Ordered `(header, block)` pairs, where
        `header` is `None` for top-level content before the first section.
    """
    blocks: list[tuple[str | None, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        next_header = _parse_section_header(line)
        if next_header is None:
            current_lines.append(line)
            continue
        if current_lines:
            blocks.append((current_header, "".join(current_lines)))
        current_header = next_header
        current_lines = [line]
    if current_lines:
        blocks.append((current_header, "".join(current_lines)))
    return blocks


def _parse_section_header(line: str) -> str | None:
    """Parse a TOML section header from a single line.

    Args:
        line: Candidate TOML line.

    Returns:
        str | None: Section name when the line is a header, otherwise `None`.
    """
    stripped = line.strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped.strip("[]")


def _strip_top_level_notify(block: str) -> str:
    """Remove top-level `notify` settings from a TOML block.

    Args:
        block: Raw TOML block content.

    Returns:
        str: Block content without top-level `notify` assignments.
    """
    return "".join(
        line for line in block.splitlines(keepends=True) if not line.lstrip().startswith("notify =")
    )


def _is_skipped_section(header: str) -> bool:
    """Report whether a TOML section should be omitted from container config.

    Args:
        header: Parsed section header without surrounding brackets.

    Returns:
        bool: `True` when the section is host-specific and should be skipped.
    """
    return (
        header == "desktop"
        or header.startswith("desktop.")
        or header.startswith("mcp_servers.node_repl")
    )
