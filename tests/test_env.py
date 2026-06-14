from __future__ import annotations

from forge.env import collect_forwarded_env, resolve_image


def test_resolve_image_precedence() -> None:
    """Prefer CLI image overrides before env and default values."""
    assert resolve_image("cli:image", {"FORGE_IMAGE": "env:image"}) == "cli:image"
    assert resolve_image(None, {"FORGE_IMAGE": "env:image"}) == "env:image"
    assert resolve_image(None, {}) == "ghcr.io/dbrennand/forge:latest"


def test_collect_forwarded_env() -> None:
    """Forward only whitelisted environment variables with non-empty values."""
    forwarded = collect_forwarded_env(
        {
            "OPENAI_API_KEY": "openai",
            "GITHUB_TOKEN": "github",
            "GH_TOKEN": "",
            "TERM": "xterm-256color",
            "LANG": "en_GB.UTF-8",
            "EXTRA": "ignored",
        }
    )

    assert forwarded == {
        "OPENAI_API_KEY": "openai",
        "GITHUB_TOKEN": "github",
        "TERM": "xterm-256color",
        "LANG": "en_GB.UTF-8",
    }
