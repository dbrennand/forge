from __future__ import annotations

from pathlib import Path

from forge.codex_config import prepare_container_config, sanitize_config


def test_sanitize_config_removes_desktop_only_settings() -> None:
    """Remove desktop-only Codex settings from mounted config content."""
    sanitized = sanitize_config(
        """model = "gpt-5.5"
notify = ["/Applications/Codex.app/Contents/Resources/bin/notify", "turn-ended"]

[mcp_servers.node_repl]
command = "/Applications/Codex.app/Contents/Resources/cua_node/bin/node_repl"

[mcp_servers.node_repl.env]
NODE_REPL_NODE_PATH = "/Applications/Codex.app/Contents/Resources/cua_node/bin/node"

[desktop]
mac-menu-bar-enabled = true

[plugins."browser@openai-bundled"]
enabled = true
"""
    )

    assert "notify = [" not in sanitized
    assert "[mcp_servers.node_repl]" not in sanitized
    assert "[mcp_servers.node_repl.env]" not in sanitized
    assert "[desktop]" not in sanitized
    assert 'model = "gpt-5.5"' in sanitized
    assert '[plugins."browser@openai-bundled"]' in sanitized


def test_prepare_container_config_returns_none_without_config(tmp_path: Path) -> None:
    """Return `None` when no host config exists to sanitize."""
    assert prepare_container_config(tmp_path) is None


def test_prepare_container_config_writes_sanitized_copy(tmp_path: Path) -> None:
    """Write a sanitized temporary config copy for container use."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """notify = ["bad"]

[mcp_servers.node_repl]
command = "/Applications/Codex.app/Contents/Resources/cua_node/bin/node_repl"

model = "gpt-5.5"
""",
        encoding="utf-8",
    )

    prepared = prepare_container_config(tmp_path)

    assert prepared is not None
    assert prepared != config_path
    assert 'notify = ["bad"]' not in prepared.read_text(encoding="utf-8")
