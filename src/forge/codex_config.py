from __future__ import annotations

import json
import shlex
import sys
import tomllib
from pathlib import Path
from typing import Any

AI_GUARDIAN_HOOK_COMMAND = "ai-guardian --ide codex"
FORGE_CODEX_MANAGED_DIR_NAME = "forge"
MANAGED_CONFIG_FILE_NAME = "config.toml"
MANAGED_HOOKS_FILE_NAME = "hooks.json"
HOOK_EVENT_ORDER = (
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
)
AI_GUARDIAN_HOOKS: dict[str, list[dict[str, Any]]] = {
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": AI_GUARDIAN_HOOK_COMMAND,
                    "timeout": 30,
                }
            ]
        }
    ],
    "PreToolUse": [
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": AI_GUARDIAN_HOOK_COMMAND,
                    "timeout": 30,
                    "statusMessage": "Checking tool permissions...",
                }
            ],
        }
    ],
    "PermissionRequest": [
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": AI_GUARDIAN_HOOK_COMMAND,
                    "timeout": 30,
                    "statusMessage": "Checking approval request...",
                }
            ],
        }
    ],
    "PostToolUse": [
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": AI_GUARDIAN_HOOK_COMMAND,
                    "timeout": 30,
                    "statusMessage": "Scanning tool output...",
                }
            ],
        }
    ],
}


def prepare_container_config(codex_home: Path) -> Path:
    """Prepare a sanitized Codex config file with AI Guardian hooks.

    Args:
        codex_home: Host Codex home directory.

    Returns:
        Path: Path to the persistent Forge-managed sanitized config file.
    """
    config_path = codex_home / "config.toml"
    _ensure_managed_codex_home_links(codex_home)
    managed_config_path = codex_home / FORGE_CODEX_MANAGED_DIR_NAME / MANAGED_CONFIG_FILE_NAME
    host_content = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    sanitized = sanitize_config(host_content)
    existing_hooks = _extract_config_hooks(sanitized)
    managed_hooks = (
        _extract_config_hooks(managed_config_path.read_text(encoding="utf-8"))
        if managed_config_path.is_file()
        else {}
    )
    merged_hooks = _merged_hooks(existing_hooks)
    merged_hooks = _carry_forward_managed_hook_state(merged_hooks, managed_hooks)
    config_without_hooks = _strip_hook_sections(sanitized)
    prepared = _merge_config_with_hooks(config_without_hooks, merged_hooks)
    return _write_managed_file(codex_home, MANAGED_CONFIG_FILE_NAME, prepared)


def prepare_container_hooks(codex_home: Path) -> Path | None:
    """Prepare a sanitized legacy Codex hooks file for compatibility.

    Args:
        codex_home: Host Codex home directory.

    Returns:
        Path | None: Path to the persistent Forge-managed hooks file, or `None`
        when the host has no usable legacy hooks file.
    """
    hooks_path = codex_home / "hooks.json"
    if not hooks_path.is_file():
        _remove_managed_file(codex_home, MANAGED_HOOKS_FILE_NAME)
        return None

    hooks_content = hooks_path.read_text(encoding="utf-8")
    if not hooks_content.strip():
        _remove_managed_file(codex_home, MANAGED_HOOKS_FILE_NAME)
        return None

    try:
        hooks_data = json.loads(hooks_content)
    except json.JSONDecodeError:
        print(
            f"Warning: ignoring invalid Codex hooks file at {hooks_path}; "
            "skipping the legacy hooks overlay.",
            file=sys.stderr,
        )
        hooks_data = {"hooks": {}}

    if not isinstance(hooks_data, dict):
        print(
            f"Warning: ignoring unexpected Codex hooks format at {hooks_path}; "
            "skipping the legacy hooks overlay.",
            file=sys.stderr,
        )
        hooks_data = {"hooks": {}}

    normalized_hooks = _normalize_legacy_hooks(hooks_data)
    sanitized_hooks = _strip_ai_guardian_from_legacy_hooks(normalized_hooks)
    if _legacy_hooks_are_empty(sanitized_hooks):
        _remove_managed_file(codex_home, MANAGED_HOOKS_FILE_NAME)
        return None

    return _write_managed_file(
        codex_home,
        MANAGED_HOOKS_FILE_NAME,
        _serialize_legacy_hooks(sanitized_hooks),
    )


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


def _extract_config_hooks(content: str) -> dict[str, Any]:
    """Extract hooks from sanitized Codex TOML content.

    Args:
        content: Sanitized `config.toml` content.

    Returns:
        dict[str, Any]: Parsed hooks mapping, or an empty mapping on parse failure.
    """
    if not content.strip():
        return {}
    try:
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return {}
    hooks = parsed.get("hooks")
    return hooks if isinstance(hooks, dict) else {}


def _strip_hook_sections(content: str) -> str:
    """Remove existing hook sections from TOML content.

    Args:
        content: Sanitized `config.toml` content.

    Returns:
        str: TOML content without any `hooks` sections.
    """
    retained_blocks: list[str] = []
    for header, block in _iter_config_blocks(content):
        if header is not None and _is_hook_section(header):
            continue
        retained_blocks.append(block)
    return "".join(retained_blocks)


def _is_hook_section(header: str) -> bool:
    """Report whether a TOML section header belongs to Codex hooks.

    Args:
        header: Parsed TOML header without surrounding brackets.

    Returns:
        bool: `True` when the section is a hook section.
    """
    return header == "hooks" or header.startswith("hooks.")


def _merged_hooks(existing: dict[str, Any]) -> dict[str, Any]:
    """Merge AI Guardian hooks into an existing Codex hooks configuration.

    Args:
        existing: Parsed hooks configuration from the host.

    Returns:
        dict[str, Any]: Merged hooks configuration for container use.
    """
    merged = dict(existing)
    for event_name in HOOK_EVENT_ORDER:
        event_hooks = AI_GUARDIAN_HOOKS[event_name]
        remaining = _filter_event_hooks(existing.get(event_name, []))
        template_entry = event_hooks[0]
        matched_entry, matched_idx = _find_matching_event_entry(remaining, template_entry)
        if matched_entry is None:
            merged[event_name] = list(event_hooks) + remaining
            continue

        updated_entry = dict(matched_entry)
        updated_entry["hooks"] = list(template_entry["hooks"]) + list(
            matched_entry.get("hooks", [])
        )
        if "matcher" in template_entry:
            updated_entry["matcher"] = template_entry["matcher"]
        else:
            updated_entry.pop("matcher", None)

        merged[event_name] = [
            updated_entry,
            *remaining[:matched_idx],
            *remaining[matched_idx + 1 :],
        ]
    return merged


def _carry_forward_managed_hook_state(
    hooks: dict[str, Any], managed_hooks: dict[str, Any]
) -> dict[str, Any]:
    """Carry forward persisted Forge-managed hook state from prior config content.

    Args:
        hooks: Newly merged hook configuration.
        managed_hooks: Existing Forge-managed hook configuration from the last run.

    Returns:
        dict[str, Any]: Hook configuration with persisted state keys copied onto
        the canonical AI Guardian entries when present.
    """
    updated_hooks = dict(hooks)
    managed_state = managed_hooks.get("state")
    if "state" not in updated_hooks and isinstance(managed_state, dict):
        updated_hooks["state"] = managed_state

    for event_name in HOOK_EVENT_ORDER:
        managed_entries = managed_hooks.get(event_name, [])
        current_entries = updated_hooks.get(event_name, [])
        if not isinstance(managed_entries, list) or not isinstance(current_entries, list):
            continue

        template_entry = AI_GUARDIAN_HOOKS[event_name][0]
        managed_entry, _ = _find_matching_event_entry(managed_entries, template_entry)
        current_entry, current_index = _find_matching_event_entry(current_entries, template_entry)
        if managed_entry is None or current_entry is None or current_index < 0:
            continue

        updated_entry = _carry_forward_managed_event_state(
            current_entry=current_entry,
            managed_entry=managed_entry,
            template_entry=template_entry,
        )

        updated_hooks[event_name] = [
            *current_entries[:current_index],
            updated_entry,
            *current_entries[current_index + 1 :],
        ]
    return updated_hooks


def _carry_forward_managed_event_state(
    *, current_entry: dict[str, Any], managed_entry: dict[str, Any], template_entry: dict[str, Any]
) -> dict[str, Any]:
    """Copy persisted managed state onto one canonical AI Guardian event entry.

    Args:
        current_entry: Newly generated canonical event entry.
        managed_entry: Existing managed event entry from the prior run.
        template_entry: Canonical template entry for the event.

    Returns:
        dict[str, Any]: Event entry with persisted managed metadata restored.
    """
    updated_entry = dict(current_entry)
    for key, value in managed_entry.items():
        if key in {"matcher", "hooks"}:
            continue
        updated_entry[key] = value

    current_hooks = current_entry.get("hooks")
    managed_hooks = managed_entry.get("hooks")
    template_hooks = template_entry.get("hooks")
    if (
        isinstance(current_hooks, list)
        and isinstance(managed_hooks, list)
        and isinstance(template_hooks, list)
    ):
        updated_entry["hooks"] = _carry_forward_managed_command_state(
            current_hooks=current_hooks,
            managed_hooks=managed_hooks,
            template_hooks=template_hooks,
        )

    return updated_entry


def _carry_forward_managed_command_state(
    *,
    current_hooks: list[Any],
    managed_hooks: list[Any],
    template_hooks: list[Any],
) -> list[Any]:
    """Copy persisted managed state onto canonical AI Guardian hook commands.

    Args:
        current_hooks: Newly generated hook commands for one event entry.
        managed_hooks: Existing managed hook commands from the prior run.
        template_hooks: Canonical hook commands for the event entry.

    Returns:
        list[Any]: Hook command list with persisted managed metadata restored.
    """
    updated_hooks = list(current_hooks)
    for template_hook in template_hooks:
        if not isinstance(template_hook, dict):
            continue

        managed_hook, _ = _find_matching_hook_command(managed_hooks, template_hook)
        current_hook, current_index = _find_matching_hook_command(updated_hooks, template_hook)
        if managed_hook is None or current_hook is None or current_index < 0:
            continue

        updated_hook = dict(current_hook)
        for key, value in managed_hook.items():
            if key in template_hook:
                continue
            updated_hook[key] = value
        updated_hooks[current_index] = updated_hook

    return updated_hooks


def _filter_event_hooks(value: Any) -> list[Any]:
    """Remove any existing AI Guardian hooks from one hook event list.

    Args:
        value: Hook event payload from the parsed JSON object.

    Returns:
        list[Any]: Hook event entries without AI Guardian commands.
    """
    if not isinstance(value, list):
        return []

    filtered: list[Any] = []
    for entry in value:
        if not isinstance(entry, dict):
            filtered.append(entry)
            continue
        if "hooks" in entry and isinstance(entry["hooks"], list):
            hooks = [hook for hook in entry["hooks"] if not _is_ai_guardian_hook(hook)]
            if hooks:
                updated_entry = dict(entry)
                updated_entry["hooks"] = hooks
                filtered.append(updated_entry)
            continue
        if _is_ai_guardian_hook(entry):
            continue
        filtered.append(entry)
    return filtered


def _find_matching_event_entry(
    entries: list[Any], template_entry: dict[str, Any]
) -> tuple[dict[str, Any] | None, int]:
    """Find the existing hook entry that matches the canonical AI Guardian matcher.

    Args:
        entries: Existing hook entries for one event.
        template_entry: Canonical AI Guardian hook entry for the event.

    Returns:
        tuple[dict[str, Any] | None, int]: The matched entry and its index, or
        `(None, -1)` when no match exists.
    """
    template_matcher = template_entry.get("matcher")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        entry_matcher = entry.get("matcher")
        if entry_matcher == template_matcher or (
            template_matcher is None and "matcher" not in entry
        ):
            return entry, index
    return None, -1


def _find_matching_hook_command(
    entries: list[Any], template_hook: dict[str, Any]
) -> tuple[dict[str, Any] | None, int]:
    """Find the existing hook command that matches the canonical AI Guardian hook.

    Args:
        entries: Existing hook command entries for one event entry.
        template_hook: Canonical AI Guardian hook command definition.

    Returns:
        tuple[dict[str, Any] | None, int]: The matched hook command and its
        index, or `(None, -1)` when no match exists.
    """
    template_type = template_hook.get("type")
    template_command = template_hook.get("command")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != template_type:
            continue
        if entry.get("command") == template_command:
            return entry, index
    return None, -1


def _normalize_legacy_hooks(content: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy Codex hooks data to the wrapped JSON schema.

    Args:
        content: Parsed legacy hooks JSON document.

    Returns:
        dict[str, Any]: Legacy hooks JSON with hook events nested under `hooks`.
    """
    hooks = content.get("hooks")
    if isinstance(hooks, dict):
        normalized = dict(content)
        normalized["hooks"] = hooks
        return normalized

    event_names = set(AI_GUARDIAN_HOOKS) | {"SessionStart", "PreCompact", "PostCompact", "Stop"}
    top_level_hooks = {key: value for key, value in content.items() if key in event_names}
    other_content = {key: value for key, value in content.items() if key not in top_level_hooks}
    if top_level_hooks:
        other_content["hooks"] = top_level_hooks
        return other_content

    return {"hooks": {}}


def _strip_ai_guardian_from_legacy_hooks(content: dict[str, Any]) -> dict[str, Any]:
    """Remove AI Guardian entries from a legacy Codex hooks JSON document.

    Args:
        content: Normalized legacy hooks JSON document.

    Returns:
        dict[str, Any]: Legacy hooks JSON without AI Guardian entries.
    """
    normalized = dict(content)
    hooks = normalized.get("hooks")
    if not isinstance(hooks, dict):
        normalized["hooks"] = {}
        return normalized

    filtered_hooks: dict[str, Any] = {}
    for event_name, event_hooks in hooks.items():
        if event_name in AI_GUARDIAN_HOOKS:
            filtered_event_hooks = _filter_event_hooks(event_hooks)
            if filtered_event_hooks:
                filtered_hooks[event_name] = filtered_event_hooks
            continue
        filtered_hooks[event_name] = event_hooks
    normalized["hooks"] = filtered_hooks
    return normalized


def _is_ai_guardian_hook(value: Any) -> bool:
    """Report whether a hook entry invokes AI Guardian.

    Args:
        value: Potential hook entry mapping.

    Returns:
        bool: `True` when the hook command resolves to AI Guardian.
    """
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    if not isinstance(command, str):
        return False
    try:
        executable = shlex.split(command)[0]
    except ValueError:
        executable = command.split(maxsplit=1)[0]
    return Path(executable).name == "ai-guardian"


def _merge_config_with_hooks(base_content: str, hooks: dict[str, Any]) -> str:
    """Combine sanitized TOML content with merged hook tables.

    Args:
        base_content: Sanitized TOML content without hook sections.
        hooks: Hook configuration mapping to append.

    Returns:
        str: Prepared `config.toml` content with a trailing newline.
    """
    hook_content = _serialize_toml_hooks(hooks)
    if not base_content.strip():
        return hook_content
    return f"{base_content.rstrip()}\n\n{hook_content}"


def _serialize_toml_hooks(content: dict[str, Any]) -> str:
    """Serialize a hooks mapping to Codex TOML tables.

    Args:
        content: Hook configuration mapping.

    Returns:
        str: Hook TOML with a trailing newline.
    """
    lines: list[str] = []
    for event_name, event_entries in _ordered_hook_events(content):
        if event_name == "state":
            continue
        if not isinstance(event_entries, list):
            continue
        for entry in event_entries:
            if not isinstance(entry, dict):
                continue
            lines.append(f"[[hooks.{event_name}]]")
            for key, value in _ordered_mapping_items(entry, primary_keys=("matcher",)):
                if key == "hooks":
                    continue
                lines.append(f"{key} = {_serialize_toml_value(value)}")
            for hook in entry.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                lines.append(f"[[hooks.{event_name}.hooks]]")
                for key, value in _ordered_mapping_items(
                    hook,
                    primary_keys=("type", "command", "timeout", "statusMessage"),
                ):
                    lines.append(f"{key} = {_serialize_toml_value(value)}")
            lines.append("")
    state_lines = _serialize_toml_hook_state(content.get("state"))
    if lines and state_lines:
        lines.append("")
    lines.extend(state_lines)
    return "\n".join(lines).rstrip() + "\n"


def _serialize_toml_hook_state(value: Any) -> list[str]:
    """Serialize Codex hook trust state tables.

    Args:
        value: Parsed `hooks.state` mapping from an existing Codex config.

    Returns:
        list[str]: TOML lines representing the hook trust state.
    """
    if not isinstance(value, dict) or not value:
        return []

    lines = ["[hooks.state]", ""]
    for state_key, state_value in sorted(value.items()):
        if not isinstance(state_key, str) or not isinstance(state_value, dict):
            continue
        lines.append(f"[hooks.state.{_serialize_toml_key(state_key)}]")
        for key, item_value in _ordered_mapping_items(state_value):
            lines.append(f"{_serialize_toml_key(key)} = {_serialize_toml_value(item_value)}")
        lines.append("")
    return lines


def _serialize_toml_key(value: str) -> str:
    """Serialize one TOML key segment.

    Args:
        value: Raw key segment.

    Returns:
        str: TOML-safe key segment.
    """
    if value.isidentifier():
        return value
    return json.dumps(value)


def _serialize_toml_value(value: Any) -> str:
    """Serialize a scalar hook value to TOML.

    Args:
        value: Value to serialize.

    Returns:
        str: TOML literal for the provided value.

    Raises:
        TypeError: If the value cannot be serialized by Forge's TOML writer.
    """
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return f"[{', '.join(_serialize_toml_value(item) for item in value)}]"
    raise TypeError(f"Unsupported TOML hook value: {value!r}")


def _serialize_legacy_hooks(content: dict[str, Any]) -> str:
    """Serialize a prepared legacy hooks mapping to canonical JSON.

    Args:
        content: Legacy hook configuration mapping.

    Returns:
        str: JSON document with a trailing newline.
    """
    return json.dumps(content, indent=2, sort_keys=True) + "\n"


def _legacy_hooks_are_empty(content: dict[str, Any]) -> bool:
    """Report whether a normalized legacy hooks document contains any hooks.

    Args:
        content: Normalized legacy hooks JSON document.

    Returns:
        bool: `True` when there are no remaining hook events to persist.
    """
    hooks = content.get("hooks")
    return not isinstance(hooks, dict) or not hooks


def _ordered_hook_events(content: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return hook events in stable serialization order.

    Args:
        content: Hook mapping to order.

    Returns:
        list[tuple[str, Any]]: Ordered `(event_name, event_entries)` pairs.
    """
    ordered_names = [event_name for event_name in HOOK_EVENT_ORDER if event_name in content]
    ordered_names.extend(
        event_name for event_name in content if event_name not in AI_GUARDIAN_HOOKS
    )
    return [(event_name, content[event_name]) for event_name in ordered_names]


def _ordered_mapping_items(
    mapping: dict[str, Any], *, primary_keys: tuple[str, ...] = ()
) -> list[tuple[str, Any]]:
    """Return mapping items in a stable key order.

    Args:
        mapping: Mapping to order.
        primary_keys: Preferred leading key order.

    Returns:
        list[tuple[str, Any]]: Ordered key-value pairs.
    """
    ordered_keys = [key for key in primary_keys if key in mapping]
    ordered_keys.extend(
        key for key in sorted(mapping) if key not in ordered_keys and key != "hooks"
    )
    if "hooks" in mapping:
        ordered_keys.append("hooks")
    return [(key, mapping[key]) for key in ordered_keys]


def _write_managed_file(codex_home: Path, name: str, content: str) -> Path:
    """Write prepared container content to a stable Forge-managed file.

    Args:
        codex_home: Host Codex home directory.
        name: File name to create inside the managed directory.
        content: File contents to write.

    Returns:
        Path: Forge-managed file path.
    """
    managed_dir = codex_home / FORGE_CODEX_MANAGED_DIR_NAME
    managed_dir.mkdir(parents=True, exist_ok=True)
    prepared_file = managed_dir / name
    if prepared_file.is_file() and prepared_file.read_text(encoding="utf-8") == content:
        return prepared_file
    prepared_file.write_text(content, encoding="utf-8")
    return prepared_file


def _remove_managed_file(codex_home: Path, name: str) -> None:
    """Remove a Forge-managed file when it is no longer active.

    Args:
        codex_home: Host Codex home directory.
        name: File name inside the managed directory.
    """
    managed_file = codex_home / FORGE_CODEX_MANAGED_DIR_NAME / name
    if managed_file.is_file() or managed_file.is_symlink():
        managed_file.unlink()


def _ensure_managed_codex_home_links(codex_home: Path) -> None:
    """Link host Codex home entries into Forge's managed Codex home.

    Args:
        codex_home: Host Codex home directory.
    """
    managed_dir = codex_home / FORGE_CODEX_MANAGED_DIR_NAME
    managed_dir.mkdir(parents=True, exist_ok=True)
    for entry in codex_home.iterdir():
        if entry.name in {
            FORGE_CODEX_MANAGED_DIR_NAME,
            MANAGED_CONFIG_FILE_NAME,
            MANAGED_HOOKS_FILE_NAME,
        }:
            continue

        managed_entry = managed_dir / entry.name
        managed_target = Path("..") / entry.name

        if managed_entry.is_symlink():
            if managed_entry.readlink() == managed_target:
                continue
            managed_entry.unlink()

        if managed_entry.exists():
            continue

        managed_entry.symlink_to(managed_target)
