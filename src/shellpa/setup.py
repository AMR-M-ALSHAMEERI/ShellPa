import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Literal

import pyfiglet
import questionary
from dotenv import dotenv_values
from rich.console import Console

from . import __version__
from .codex_install import (
    codex_install_command,
    format_command,
    install_codex_sdk,
)
from .codex_provider import codex_sdk_installed
from .credentials import (
    PROVIDER_API_KEYS,
    CredentialStore,
    CredentialStoreError,
    set_session_credential,
)
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


ASSIGNMENT_PATTERN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _safe_config_value(value: str) -> str:
    normalized = value.strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise ValueError("Configuration values must be non-empty single lines.")
    return normalized


def _update_config_file(
    path: Path,
    updates: dict[str, str],
    *,
    remove: set[str] | None = None,
) -> None:
    """Update named metadata while preserving unrelated configuration lines."""
    removals = remove or set()
    pending = {name: _safe_config_value(value) for name, value in updates.items()}
    existing_lines = (
        path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    )
    output: list[str] = []
    written: set[str] = set()
    for line in existing_lines:
        match = ASSIGNMENT_PATTERN.match(line)
        name = match.group(1) if match else None
        if name in removals:
            continue
        if name in pending:
            if name not in written:
                output.append(f"{name}={pending[name]}")
                written.add(name)
            continue
        output.append(line)
    for name, value in pending.items():
        if name not in written:
            output.append(f"{name}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write("\n".join(output).rstrip() + "\n")
        temporary = Path(stream.name)
    try:
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _saved_config(path: Path) -> dict[str, str | None]:
    if not path.is_file():
        return {}
    return dict(dotenv_values(path))


def _select_legacy_action(backend_name: str, *, allow_session: bool) -> str | None:
    choices = [
        questionary.Choice(f"Move it to {backend_name} (Recommended)", value="migrate"),
    ]
    if allow_session:
        choices.append(
            questionary.Choice("Use it for this ShellPa process", value="session")
        )
    choices.extend(
        [
            questionary.Choice("Remove it and enter a new key", value="remove"),
            questionary.Choice("Return to provider selection", value="back"),
        ]
    )
    choice = questionary.select(
        "A legacy plaintext API key was found. What would you like to do?",
        choices=choices,
        style=ocean_theme,
    ).ask()
    return check_cancel(choice)


def _configure_api_credential(
    provider: str,
    env_path: Path,
    store: CredentialStore,
    *,
    allow_session: bool = True,
) -> Literal["keyring", "session", "legacy_session", "back"] | None:
    key_name = PROVIDER_API_KEYS[provider]
    saved = _saved_config(env_path)
    legacy_value = saved.get(key_name)
    backend = store.status()

    if isinstance(legacy_value, str) and legacy_value.strip():
        if backend.available:
            action = _select_legacy_action(
                backend.name,
                allow_session=allow_session,
            )
        else:
            console.print(
                f"[yellow]{backend.detail} The legacy key will not be copied "
                "into another plaintext file.[/yellow]"
            )
            choices = []
            if allow_session:
                choices.append(
                    questionary.Choice(
                        "Use the legacy key for this ShellPa process",
                        value="session",
                    )
                )
            choices.extend(
                [
                    questionary.Choice("Remove it and enter a new key", value="remove"),
                    questionary.Choice("Return to provider selection", value="back"),
                ]
            )
            action = questionary.select(
                "How should ShellPa continue?",
                choices=choices,
                style=ocean_theme,
            ).ask()
            action = check_cancel(action)

        if action is None:
            return None
        if action == "RETRY":
            return _configure_api_credential(
                provider,
                env_path,
                store,
                allow_session=allow_session,
            )
        if action == "back":
            return "back"
        if action == "session":
            set_session_credential(provider, legacy_value)
            return "legacy_session"
        if action == "migrate":
            try:
                store.set(provider, legacy_value)
                if store.get(provider) != legacy_value.strip():
                    raise CredentialStoreError("Credential verification failed.")
            except CredentialStoreError as exc:
                console.print(f"[red]{exc} The legacy value was not removed.[/red]")
            else:
                _update_config_file(
                    env_path,
                    {"SHELLPA_CREDENTIAL_STORE": "keyring"},
                    remove=set(PROVIDER_API_KEYS.values()),
                )
                console.print(
                    f"[green]Credential moved to {backend.name}; plaintext copy removed.[/green]"
                )
                return "keyring"
        if action == "remove":
            _update_config_file(env_path, {}, remove={key_name})

    saved_provider = (saved.get("SHELLPA_PROVIDER") or "").strip().lower()
    saved_source = (saved.get("SHELLPA_CREDENTIAL_STORE") or "").strip().lower()
    if saved_provider == provider and saved_source == "keyring" and backend.available:
        action = questionary.select(
            f"A {provider} credential is already stored securely.",
            choices=[
                questionary.Choice("Keep existing credential", value="keep"),
                questionary.Choice("Replace credential", value="replace"),
                questionary.Choice("Remove and replace credential", value="remove"),
                questionary.Choice("Return to provider selection", value="back"),
            ],
            style=ocean_theme,
        ).ask()
        action = check_cancel(action)
        if action is None:
            return None
        if action == "back":
            return "back"
        if action == "keep":
            try:
                store.get(provider)
            except CredentialStoreError:
                console.print(
                    "[yellow]The secure credential is missing. Enter a replacement.[/yellow]"
                )
            else:
                return "keyring"
        if action == "remove":
            try:
                store.delete(provider)
            except CredentialStoreError as exc:
                console.print(f"[red]{exc}[/red]")
                return None

    if backend.available:
        console.print(f"[dim]Secure storage: {backend.name}[/dim]")
    else:
        console.print(f"[yellow]{backend.detail}[/yellow]")

    while True:
        api_key = questionary.password(
            f"Enter your {provider.capitalize()} API Key:", style=ocean_theme
        ).ask()
        api_key = check_cancel(api_key)
        if api_key is None:
            return None
        if api_key == "RETRY":
            continue
        api_key = api_key.strip()
        if not api_key:
            console.print("[red]API key cannot be empty.[/red]")
            continue

        if backend.available:
            try:
                store.set(provider, api_key)
                if store.get(provider) != api_key:
                    raise CredentialStoreError("Credential verification failed.")
            except CredentialStoreError as exc:
                console.print(f"[red]{exc}[/red]")
                continue
            console.print(f"[green]Credential stored in {backend.name}.[/green]")
            return "keyring"

        choices = []
        if allow_session:
            choices.append(
                questionary.Choice(
                    "Use this key for this ShellPa process", value="session"
                )
            )
        choices.append(questionary.Choice("Return to provider selection", value="back"))
        choice = questionary.select(
            "Secure persistence is unavailable.",
            choices=choices,
            style=ocean_theme,
        ).ask()
        choice = check_cancel(choice)
        if choice == "session":
            set_session_credential(provider, api_key)
            return "session"
        if choice in {None, "back"}:
            return choice


def _select_recovery_preference(provider: str) -> str | None:
    """Offer a persistent recovery privacy choice during interactive config."""
    if not _interactive_terminal():
        return None
    choice = questionary.select(
        "How should automatic command recovery use redacted failure details?",
        choices=[
            questionary.Choice("Ask before recovery (Recommended)", value="ask"),
            questionary.Choice(
                f"Always allow minimal recovery for {provider}", value="allow"
            ),
            questionary.Choice("Turn automatic recovery off", value="off"),
        ],
        style=ocean_theme,
    ).ask()
    return check_cancel(choice)


def run_setup_wizard(
    store: CredentialStore | None = None,
    *,
    allow_session: bool = True,
) -> bool:
    credential_store = store or CredentialStore()
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

        credential_source: str | None = None
        if provider != "codex":
            credential_source = _configure_api_credential(
                provider,
                get_env_path(),
                credential_store,
                allow_session=allow_session,
            )
            if credential_source is None:
                return False
            if credential_source == "back":
                continue

        break  # break main loop

    env_path = get_env_path()
    recovery_preference = _select_recovery_preference(provider)
    if recovery_preference == "RETRY":
        recovery_preference = "ask"
    provider_permission_name = (
        "SHELLPA_RECOVERY_PERMISSION_"
        + re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
    )
    updates = {
        "SHELLPA_MODEL": model,
        "SHELLPA_PROVIDER": provider,
    }
    recovery_removals: set[str] = set()
    if recovery_preference == "ask":
        recovery_removals.update(
            {"SHELLPA_RECOVERY_PERMISSION", provider_permission_name}
        )
    elif recovery_preference == "allow":
        updates[provider_permission_name] = "allow"
        recovery_removals.add("SHELLPA_RECOVERY_PERMISSION")
    elif recovery_preference == "off":
        updates["SHELLPA_RECOVERY_PERMISSION"] = "off"
        recovery_removals.add(provider_permission_name)
    if credential_source == "keyring":
        updates["SHELLPA_CREDENTIAL_STORE"] = "keyring"
    _update_config_file(
        env_path,
        updates,
        remove=(
            (
                set()
                if credential_source == "legacy_session"
                else set(PROVIDER_API_KEYS.values())
            )
            | (
                {"SHELLPA_CREDENTIAL_STORE"}
                if credential_source != "keyring"
                else set()
            )
            | recovery_removals
        ),
    )

    os.environ["SHELLPA_MODEL"] = model
    os.environ["SHELLPA_PROVIDER"] = provider
    if credential_source == "keyring":
        os.environ["SHELLPA_CREDENTIAL_STORE"] = "keyring"
    else:
        os.environ.pop("SHELLPA_CREDENTIAL_STORE", None)
    if recovery_preference == "ask":
        os.environ.pop("SHELLPA_RECOVERY_PERMISSION", None)
        os.environ.pop(provider_permission_name, None)
    elif recovery_preference == "allow":
        os.environ.pop("SHELLPA_RECOVERY_PERMISSION", None)
        os.environ[provider_permission_name] = "allow"
    elif recovery_preference == "off":
        os.environ["SHELLPA_RECOVERY_PERMISSION"] = "off"
        os.environ.pop(provider_permission_name, None)

    console.print("\n[bold green]Configuration saved successfully! ✨[/bold green]")
    if provider == "codex":
        if codex_sdk_installed():
            _offer_codex_login()
        else:
            command = format_command(codex_install_command())
            console.print(f"[cyan]When you are ready, run: {command}[/cyan]")
            console.print("[dim]Then start sign-in with: shellpa login[/dim]")
    return True
