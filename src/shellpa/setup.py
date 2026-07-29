import os
import sys
from pathlib import Path
from typing import Literal

import pyfiglet
import questionary
from rich.console import Console

from . import __version__
from .codex_install import (
    codex_install_command,
    format_command,
    install_codex_sdk,
)
from .codex_provider import codex_sdk_installed
from .icons import provider_icon

console = Console()

# Defined styled theme matching our Ocean/Aurora aesthetics
ocean_theme = questionary.Style(
    [
        ("qmark", "fg:#00ffff bold"),  # Cyan question mark
        ("question", "fg:#ffffff bold"),  # White question text
        ("answer", "fg:#00ccff bold"),  # Light blue selected answer
        ("pointer", "fg:#00ffff bold"),  # Cyan pointer
        ("highlighted", "fg:#0055ff bold"),  # Royal blue for highlighted choice
        ("selected", "fg:#00ccff"),  # Cyan for selected items in list
        ("separator", "fg:#003366"),  # Navy blue separator
        ("instruction", "fg:#0077ff"),  # Instruction text
        ("text", "fg:#ffffff"),  # Normal text
    ]
)


def get_env_path() -> Path:
    """Return the global configuration path"""
    return Path.home() / ".shellpa.env"


def check_cancel(value):
    """Check if a prompt returned None (user pressed Ctrl+C) and ask for confirmation."""
    if value is not None:
        return value

    # If we get here, they pressed Ctrl+C
    confirm = questionary.confirm(
        "Are you sure you want to cancel the setup?", style=ocean_theme, default=True
    ).ask()

    if confirm:
        console.print("[red]Setup cancelled by user.[/red]")
        return None
    else:
        # They don't want to cancel, but we'd need to re-prompt them.
        # To avoid complex loops for every step, we return "RETRY" or False
        return "RETRY"


def _interactive_terminal() -> bool:
    """Return whether setup can safely offer state-changing interactive actions."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prepare_codex_provider() -> Literal["ready", "later", "back"] | None:
    """Offer an explicit install choice before Codex configuration is saved."""
    if codex_sdk_installed():
        return "ready"

    command = format_command(codex_install_command())
    if not _interactive_terminal():
        console.print(
            "[yellow]Codex is not installed. Automatic installation is disabled "
            "outside an interactive terminal.[/yellow]"
        )
        console.print(f"[dim]Run this when you are ready: {command}[/dim]")
        return "later"

    while True:
        choice = questionary.select(
            "The embedded Codex provider is required. What would you like to do?",
            choices=[
                questionary.Choice("Install now (Recommended)", value="install"),
                questionary.Choice("Not now", value="later"),
                questionary.Choice(
                    "Return to provider selection",
                    value="back",
                ),
            ],
            style=ocean_theme,
        ).ask()
        choice = check_cancel(choice)
        if choice is None:
            return None
        if choice == "RETRY":
            continue
        if choice in {"later", "back"}:
            return choice
        if install_codex_sdk(console):
            return "ready"


def _offer_codex_login() -> None:
    """Offer Codex-managed sign-in after the provider is available."""
    if not _interactive_terminal() or not codex_sdk_installed():
        return

    from .codex_auth import login_codex_interactively

    login_codex_interactively(console, device_code=None)


def run_setup_wizard():
    console.print()
    banner_text = pyfiglet.figlet_format("SHELLPA", font="slant")
    banner_text = f"{banner_text.rstrip()}  v{__version__}\n"
    console.print(f"[bold #00ccff]{banner_text}[/bold #00ccff]")

    console.print("[bold cyan]Welcome to ShellPa Setup Wizard! 🚀[/bold cyan]")
    console.print("[dim]Let's configure your AI provider and model.[/dim]\n")

    while True:
        # 1. Choose Provider
        provider = questionary.select(
            "Select your AI Provider:",
            choices=[
                questionary.Choice(
                    f"{provider_icon('openrouter')} OpenRouter (Recommended)",
                    value="openrouter",
                ),
                questionary.Choice(
                    f"{provider_icon('openai')} OpenAI",
                    value="openai",
                ),
                questionary.Choice(
                    f"{provider_icon('codex')} OpenAI Codex (ChatGPT subscription)",
                    value="codex",
                ),
                questionary.Choice(
                    f"{provider_icon('gemini')} Google Gemini",
                    value="gemini",
                ),
                questionary.Choice(
                    f"{provider_icon('anthropic')} Anthropic",
                    value="anthropic",
                ),
            ],
            style=ocean_theme,
        ).ask()

        provider = check_cancel(provider)
        if provider is None:
            return False
        if provider == "RETRY":
            continue

        # 2. Choose Model based on provider
        while True:
            model_choices: list[questionary.Choice | str] = []
            if provider == "openrouter":
                model_choices = [
                    questionary.Choice(
                        "openai/gpt-3.5-turbo (Recommended)",
                        value="openrouter/openai/gpt-3.5-turbo",
                    ),
                    questionary.Choice(
                        "anthropic/claude-3-haiku",
                        value="openrouter/anthropic/claude-3-haiku",
                    ),
                    questionary.Choice(
                        "google/gemini-flash-1.5",
                        value="openrouter/google/gemini-flash-1.5",
                    ),
                ]
            elif provider == "openai":
                model_choices = ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
            elif provider == "codex":
                model_choices = [
                    questionary.Choice(
                        "Use the Codex account default (Recommended)",
                        value="codex/default",
                    )
                ]
            elif provider == "gemini":
                model_choices = [
                    "gemini/gemini-1.5-pro",
                    "gemini/gemini-1.5-flash",
                    "gemini/gemini-pro",
                ]
            elif provider == "anthropic":
                model_choices = [
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "claude-3-haiku-20240307",
                ]

            model_choices.append(questionary.Choice("Custom Model...", value="custom"))

            model = questionary.select(
                "Select the model:", choices=model_choices, style=ocean_theme
            ).ask()

            model = check_cancel(model)
            if model is None:
                return False
            if model == "RETRY":
                continue

            if model == "custom":
                while True:
                    custom_model = questionary.text(
                        "Enter your custom model string (e.g. ollama/mistral):",
                        style=ocean_theme,
                    ).ask()

                    custom_model = check_cancel(custom_model)
                    if custom_model is None:
                        return False
                    if custom_model == "RETRY":
                        continue
                    model = custom_model  # update model variable
                    break
            break  # break model loop

        if provider == "codex":
            codex_state = _prepare_codex_provider()
            if codex_state is None:
                return False
            if codex_state == "back":
                continue

        # 3. Enter an API key only for providers that require one.
        api_key_name: str | None = None
        api_key: str | None = None
        while provider != "codex":
            api_key_name = ""
            if provider == "openrouter":
                api_key_name = "OPENROUTER_API_KEY"
            elif provider == "openai":
                api_key_name = "OPENAI_API_KEY"
            elif provider == "gemini":
                api_key_name = "GEMINI_API_KEY"
            elif provider == "anthropic":
                api_key_name = "ANTHROPIC_API_KEY"

            api_key = questionary.password(
                f"Enter your {provider.capitalize()} API Key:", style=ocean_theme
            ).ask()

            api_key = check_cancel(api_key)
            if api_key is None:
                return False
            if api_key == "RETRY":
                continue
            api_key = api_key.strip()
            if not api_key:
                console.print("[red]API key cannot be empty.[/red]")
                continue
            break  # break api loop

        break  # break main loop

    # Save to global config
    env_path = get_env_path()

    # Read existing if any
    env_vars = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env_vars[k] = v

    # Update config
    env_vars["SHELLPA_MODEL"] = model
    env_vars["SHELLPA_PROVIDER"] = provider
    if api_key_name is not None and api_key is not None:
        env_vars[api_key_name] = api_key

    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    # Load into current environment immediately
    os.environ["SHELLPA_MODEL"] = model
    os.environ["SHELLPA_PROVIDER"] = provider
    if api_key_name is not None and api_key is not None:
        os.environ[api_key_name] = api_key

    console.print("\n[bold green]Configuration saved successfully! ✨[/bold green]")
    if provider == "codex":
        if codex_sdk_installed():
            _offer_codex_login()
        else:
            command = format_command(codex_install_command())
            console.print(f"[cyan]When you are ready, run: {command}[/cyan]")
            console.print("[dim]Then start sign-in with: shellpa login[/dim]")
    return True
