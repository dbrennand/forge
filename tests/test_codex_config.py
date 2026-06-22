from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from forge.codex_config import (
    AI_GUARDIAN_HOOK_COMMAND,
    prepare_container_config,
    prepare_container_hooks,
    sanitize_config,
)


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


def test_prepare_container_config_generates_ai_guardian_hooks_without_host_config(
    tmp_path: Path,
) -> None:
    """Generate a config file containing the canonical Codex hook tables."""
    prepared = prepare_container_config(tmp_path)
    assert prepared == tmp_path / "forge" / "config.toml"

    parsed = tomllib.loads(prepared.read_text(encoding="utf-8"))

    assert parsed["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == AI_GUARDIAN_HOOK_COMMAND
    assert parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == AI_GUARDIAN_HOOK_COMMAND
    assert (
        parsed["hooks"]["PermissionRequest"][0]["hooks"][0]["command"] == AI_GUARDIAN_HOOK_COMMAND
    )
    assert parsed["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == AI_GUARDIAN_HOOK_COMMAND


def test_prepare_container_config_writes_sanitized_copy_with_merged_hooks(tmp_path: Path) -> None:
    """Write a sanitized managed config copy and prepend AI Guardian hooks."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """notify = ["bad"]
model = "gpt-5.5"

[mcp_servers.node_repl]
command = "/Applications/Codex.app/Contents/Resources/cua_node/bin/node_repl"

[[hooks.PreToolUse]]
matcher = "^Bash$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "other-hook"
timeout = 10
""",
        encoding="utf-8",
    )

    prepared = prepare_container_config(tmp_path)
    parsed = tomllib.loads(prepared.read_text(encoding="utf-8"))

    assert prepared != config_path
    assert prepared == tmp_path / "forge" / "config.toml"
    assert 'notify = ["bad"]' not in prepared.read_text(encoding="utf-8")
    assert "[mcp_servers.node_repl]" not in prepared.read_text(encoding="utf-8")
    assert parsed["model"] == "gpt-5.5"
    assert parsed["hooks"]["PreToolUse"][0]["matcher"] == ".*"
    assert parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == AI_GUARDIAN_HOOK_COMMAND
    assert parsed["hooks"]["PreToolUse"][1]["matcher"] == "^Bash$"
    assert parsed["hooks"]["PreToolUse"][1]["hooks"][0]["command"] == "other-hook"


def test_prepare_container_config_deduplicates_existing_ai_guardian_hooks(tmp_path: Path) -> None:
    """Replace prior AI Guardian config entries with the canonical hook definition."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""[[hooks.PreToolUse]]
matcher = ".*"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "{AI_GUARDIAN_HOOK_COMMAND}"
timeout = 5

[[hooks.PreToolUse.hooks]]
type = "command"
command = "other-hook"
timeout = 10
""",
        encoding="utf-8",
    )

    prepared = prepare_container_config(tmp_path)
    parsed = tomllib.loads(prepared.read_text(encoding="utf-8"))

    hooks = parsed["hooks"]["PreToolUse"][0]["hooks"]
    assert hooks[0]["command"] == AI_GUARDIAN_HOOK_COMMAND
    assert hooks[0]["timeout"] == 30
    assert hooks[1]["command"] == "other-hook"


def test_prepare_container_config_does_not_rewrite_unchanged_managed_file(tmp_path: Path) -> None:
    """Reuse the managed config file when the generated content is unchanged."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.5"\n', encoding="utf-8")

    prepared = prepare_container_config(tmp_path)
    original_mtime_ns = prepared.stat().st_mtime_ns

    rewritten = prepare_container_config(tmp_path)

    assert rewritten == prepared
    assert rewritten.stat().st_mtime_ns == original_mtime_ns


def test_prepare_container_config_carries_forward_managed_trusted_hash(tmp_path: Path) -> None:
    """Preserve persisted hook trust state from the managed config file."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.5"\n', encoding="utf-8")
    managed_dir = tmp_path / "forge"
    managed_dir.mkdir()
    (managed_dir / "config.toml").write_text(
        f"""model = "gpt-5.5"

[[hooks.PreToolUse]]
matcher = ".*"
trusted_hash = "persist-me"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "{AI_GUARDIAN_HOOK_COMMAND}"
timeout = 30
statusMessage = "Checking tool permissions..."
""",
        encoding="utf-8",
    )

    prepared = prepare_container_config(tmp_path)
    parsed = tomllib.loads(prepared.read_text(encoding="utf-8"))

    assert parsed["hooks"]["PreToolUse"][0]["trusted_hash"] == "persist-me"


def test_prepare_container_config_carries_forward_managed_nested_hook_state(tmp_path: Path) -> None:
    """Preserve persisted hook state stored on the AI Guardian command entry."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.5"\n', encoding="utf-8")
    managed_dir = tmp_path / "forge"
    managed_dir.mkdir()
    (managed_dir / "config.toml").write_text(
        f"""model = "gpt-5.5"

[[hooks.PreToolUse]]
matcher = ".*"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "{AI_GUARDIAN_HOOK_COMMAND}"
timeout = 30
statusMessage = "Checking tool permissions..."
enabled = true
trusted_hash = "persist-me"
state = "approved"
""",
        encoding="utf-8",
    )

    prepared = prepare_container_config(tmp_path)
    parsed = tomllib.loads(prepared.read_text(encoding="utf-8"))

    managed_hook = parsed["hooks"]["PreToolUse"][0]["hooks"][0]
    assert managed_hook["enabled"] is True
    assert managed_hook["trusted_hash"] == "persist-me"
    assert managed_hook["state"] == "approved"


def test_prepare_container_config_carries_forward_managed_hooks_state_table(
    tmp_path: Path,
) -> None:
    """Preserve Codex hook trust state stored in the managed hooks state table."""
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.5"\n', encoding="utf-8")
    managed_dir = tmp_path / "forge"
    managed_dir.mkdir()
    (managed_dir / "config.toml").write_text(
        f"""model = "gpt-5.5"

[[hooks.PreToolUse]]
matcher = ".*"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "{AI_GUARDIAN_HOOK_COMMAND}"
timeout = 30
statusMessage = "Checking tool permissions..."

[hooks.state]

[hooks.state."/home/forge/.codex/forge/config.toml:pre_tool_use:0:0"]
trusted_hash = "sha256:persist-me"
""",
        encoding="utf-8",
    )

    prepared = prepare_container_config(tmp_path)
    parsed = tomllib.loads(prepared.read_text(encoding="utf-8"))

    state = parsed["hooks"]["state"]
    assert (
        state["/home/forge/.codex/forge/config.toml:pre_tool_use:0:0"]["trusted_hash"]
        == "sha256:persist-me"
    )


def test_prepare_container_config_links_host_auth_into_managed_codex_home(tmp_path: Path) -> None:
    """Link host auth into the managed Codex home used inside the container."""
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("{}", encoding="utf-8")

    prepare_container_config(tmp_path)

    managed_auth = tmp_path / "forge" / "auth.json"
    assert managed_auth.is_symlink()
    assert managed_auth.readlink() == Path("..") / "auth.json"


def test_prepare_container_hooks_returns_none_without_host_file(tmp_path: Path) -> None:
    """Skip the legacy compatibility overlay when no legacy hooks file exists."""
    assert prepare_container_hooks(tmp_path) is None


def test_prepare_container_hooks_ignores_stale_managed_file_without_host_file(
    tmp_path: Path,
) -> None:
    """Remove a stale managed hooks file when the host legacy file is absent."""
    managed_dir = tmp_path / "forge"
    managed_dir.mkdir()
    stale_hooks = managed_dir / "hooks.json"
    stale_hooks.write_text("{}", encoding="utf-8")

    assert prepare_container_hooks(tmp_path) is None
    assert not stale_hooks.exists()


def test_prepare_container_hooks_returns_none_when_sanitized_hooks_are_empty(
    tmp_path: Path,
) -> None:
    """Skip the legacy overlay when no non-AI Guardian legacy hooks remain."""
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text('{"hooks": {}}', encoding="utf-8")
    managed_dir = tmp_path / "forge"
    managed_dir.mkdir()
    stale_hooks = managed_dir / "hooks.json"
    stale_hooks.write_text('{"hooks": {}}', encoding="utf-8")

    assert prepare_container_hooks(tmp_path) is None
    assert not stale_hooks.exists()


def test_prepare_container_hooks_treats_empty_host_file_as_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skip empty legacy hooks files without warning about invalid JSON."""
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text("", encoding="utf-8")
    managed_dir = tmp_path / "forge"
    managed_dir.mkdir()
    stale_hooks = managed_dir / "hooks.json"
    stale_hooks.write_text('{"hooks": {}}', encoding="utf-8")

    assert prepare_container_hooks(tmp_path) is None
    captured = capsys.readouterr()

    assert captured.err == ""
    assert not stale_hooks.exists()


def test_prepare_container_hooks_preserves_unrelated_existing_hooks(tmp_path: Path) -> None:
    """Preserve unrelated legacy hooks while stripping AI Guardian duplicates."""
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": ".*",
                            "hooks": [
                                {"type": "command", "command": "ai-guardian"},
                                {"type": "command", "command": "other-hook --pre"},
                            ],
                        }
                    ],
                    "CustomEvent": [{"hooks": [{"command": "leave-me-alone"}]}],
                }
            }
        ),
        encoding="utf-8",
    )

    prepared = prepare_container_hooks(tmp_path)
    assert prepared is not None
    assert prepared == tmp_path / "forge" / "hooks.json"
    hooks = json.loads(prepared.read_text(encoding="utf-8"))

    assert hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "other-hook --pre"
    assert hooks["hooks"]["CustomEvent"] == [{"hooks": [{"command": "leave-me-alone"}]}]


def test_prepare_container_hooks_wraps_top_level_legacy_events(tmp_path: Path) -> None:
    """Normalize top-level legacy events into the wrapped Codex hooks schema."""
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text(
        json.dumps(
            {
                "PreToolUse": [{"matcher": "^Bash$", "hooks": [{"command": "other-hook"}]}],
                "SessionStart": [{"hooks": [{"command": "start-hook"}]}],
            }
        ),
        encoding="utf-8",
    )

    prepared = prepare_container_hooks(tmp_path)
    assert prepared is not None
    assert prepared == tmp_path / "forge" / "hooks.json"
    hooks = json.loads(prepared.read_text(encoding="utf-8"))

    assert hooks["hooks"]["PreToolUse"][0]["matcher"] == "^Bash$"
    assert hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "start-hook"


def test_prepare_container_hooks_warns_and_falls_back_for_invalid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Warn and skip the legacy overlay when the host JSON is invalid."""
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text("{not json", encoding="utf-8")

    prepared = prepare_container_hooks(tmp_path)
    assert prepared is None
    captured = capsys.readouterr()

    assert "invalid Codex hooks file" in captured.err


def test_prepare_container_hooks_warns_and_falls_back_for_unexpected_json_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Warn and skip the legacy overlay when the host JSON is not an object."""
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text(json.dumps(["unexpected"]), encoding="utf-8")

    prepared = prepare_container_hooks(tmp_path)
    assert prepared is None
    captured = capsys.readouterr()

    assert "unexpected Codex hooks format" in captured.err
