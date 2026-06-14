from __future__ import annotations

import tempfile
from pathlib import Path


def prepare_container_config(codex_home: Path) -> Path | None:
    config_path = codex_home / "config.toml"
    if not config_path.is_file():
        return None

    sanitized = sanitize_config(config_path.read_text(encoding="utf-8"))
    temp_dir = Path(tempfile.mkdtemp(prefix="forge-codex-config-"))
    prepared_config = temp_dir / "config.toml"
    prepared_config.write_text(sanitized, encoding="utf-8")
    return prepared_config


def sanitize_config(content: str) -> str:
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
    stripped = line.strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped.strip("[]")


def _strip_top_level_notify(block: str) -> str:
    return "".join(
        line for line in block.splitlines(keepends=True) if not line.lstrip().startswith("notify =")
    )


def _is_skipped_section(header: str) -> bool:
    return header == "desktop" or header.startswith("desktop.") or header.startswith(
        "mcp_servers.node_repl"
    )
