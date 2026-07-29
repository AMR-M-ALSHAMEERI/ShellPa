"""Terminal-native ShellPa icons with reliable ASCII fallbacks."""

from __future__ import annotations

import os
import sys

PROVIDER_ICONS = {
    "openai": ("◉", "[OpenAI]"),
    "codex": ("◉", "[Codex]"),
    "openrouter": ("◇", "[OpenRouter]"),
    "gemini": ("✦", "[Gemini]"),
    "anthropic": ("◆", "[Anthropic]"),
}

SHELL_ICONS = {
    "powershell": ("❯", "[PS]"),
    "pwsh": ("❯", "[PS]"),
    "cmd": (">_", "[CMD]"),
    "bash": ("$", "[Bash]"),
    "zsh": ("%", "[Zsh]"),
    "fish": ("><", "[Fish]"),
}

UI_ICONS = {
    "assistant": ("✦", "*"),
    "success": ("✓", "OK"),
    "caution": ("!", "!"),
    "failure": ("✕", "X"),
    "theme": ("◈", "*"),
}


def unicode_icons_supported() -> bool:
    if os.environ.get("SHELLPA_ICONS", "").strip().lower() == "ascii":
        return False
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "◉✦◆❯✓".encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def _select(pair: tuple[str, str]) -> str:
    return pair[0] if unicode_icons_supported() else pair[1]


def provider_icon(provider: str | None) -> str:
    return _select(PROVIDER_ICONS.get((provider or "").lower(), ("●", "[AI]")))


def shell_icon(shell: str | None) -> str:
    return _select(SHELL_ICONS.get((shell or "").lower(), ("›", "[Shell]")))


def ui_icon(name: str) -> str:
    return _select(UI_ICONS.get(name, ("•", "*")))


def provider_for_model(model_name: str | None) -> str | None:
    normalized = (model_name or "").lower()
    if normalized.startswith("openrouter/"):
        return "openrouter"
    if normalized.startswith("codex/"):
        return "codex"
    if normalized.startswith(("openai/", "gpt-", "o1", "o3", "o4")):
        return "openai"
    if normalized.startswith(("gemini/", "gemini-")):
        return "gemini"
    if normalized.startswith(("anthropic/", "claude-")):
        return "anthropic"
    return None


def model_icon(model_name: str | None) -> str:
    return provider_icon(provider_for_model(model_name))
