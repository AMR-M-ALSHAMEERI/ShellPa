import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

import questionary
from dotenv import dotenv_values
from rich.console import Console

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
from .identity import MICRO_MARK
from .input_ui import InputAction, prompt_input
from .selector import (
    SelectionOption,
    SelectorAction,
    SelectorResult,
    select_interactively,
)
from .ux import UXSettings, brand_logo_text, load_ux_settings

console = Console()

PROVIDER_ORDER = ("openrouter", "openai", "codex", "gemini", "anthropic")
PROVIDER_LABELS = {
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "codex": "OpenAI Codex",
    "gemini": "Google Gemini",
    "anthropic": "Anthropic",
}
PROVIDER_DESCRIPTIONS = {
    "openrouter": "Use one API key with models from multiple providers.",
    "openai": "Use an OpenAI API key and OpenAI model.",
    "codex": "Use a ChatGPT subscription through the embedded Codex runtime.",
    "gemini": "Use a Google Gemini API key and Gemini model.",
    "anthropic": "Use an Anthropic API key and Claude model.",
}
PROVIDER_MODELS = {
    "openrouter": (
        "openrouter/openai/gpt-3.5-turbo",
        "openrouter/anthropic/claude-3-haiku",
        "openrouter/google/gemini-flash-1.5",
    ),
    "openai": ("gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"),
    "codex": ("codex/default",),
    "gemini": (
        "gemini/gemini-1.5-pro",
        "gemini/gemini-1.5-flash",
        "gemini/gemini-pro",
    ),
    "anthropic": (
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ),
}
CUSTOM_MODEL = "__custom__"


class SetupOutcome(str, Enum):
    SAVED = "saved"
    CANCELLED = "cancelled"
    FAILED = "failed"


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


def _native_selector_available() -> bool:
    """Keep the native UI independently testable from state-changing prompts."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def select_provider_interactively(
    current: str,
    settings: UXSettings,
    *,
    input_stream=None,
    output_stream=None,
) -> SelectorResult[str]:
    options = tuple(
        SelectionOption(
            provider,
            (
                f"{provider_icon(provider)} {PROVIDER_LABELS[provider]}"
                + (" (Recommended)" if provider == "openrouter" else "")
            ),
            PROVIDER_DESCRIPTIONS[provider],
        )
        for provider in PROVIDER_ORDER
    )
    selected = current if current in PROVIDER_ORDER else PROVIDER_ORDER[0]
    return select_interactively(
        "Choose provider",
        options,
        selected,
        settings,
        persisted_value=selected,
        allow_back=True,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def select_model_interactively(
    provider: str,
    current: str | None,
    settings: UXSettings,
    *,
    input_stream=None,
    output_stream=None,
) -> SelectorResult[str]:
    available = PROVIDER_MODELS[provider]
    selected = current or available[0]
    model_options = [SelectionOption(model, model) for model in available]
    if current and current not in available:
        model_options.insert(
            0,
            SelectionOption(current, current, "Saved custom model."),
        )
    options = tuple(
        model_options
        + [SelectionOption(CUSTOM_MODEL, "Custom model…", "Enter a provider model ID.")]
    )
    while True:
        result = select_interactively(
            "Choose model",
            options,
            selected,
            settings,
            persisted_value=selected,
            allow_back=True,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if result.action is not SelectorAction.SELECT or result.value != CUSTOM_MODEL:
            return result
        custom = prompt_input(
            "Custom model",
            settings,
            description="Enter the exact model identifier expected by your provider.",
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if custom.action is InputAction.SUBMIT and custom.value is not None:
            return SelectorResult(SelectorAction.SELECT, custom.value)
        if custom.action is InputAction.CANCEL:
            return SelectorResult(SelectorAction.CANCEL)


def select_recovery_interactively(
    provider: str,
    current: str,
    settings: UXSettings,
    *,
    input_stream=None,
    output_stream=None,
) -> SelectorResult[str]:
    options = (
        SelectionOption(
            "ask",
            "Ask before recovery",
            "Review each redacted provider recovery request before it is sent.",
        ),
        SelectionOption(
            "allow",
            f"Allow minimal recovery for {provider}",
            "Reuse the explicit permission for this provider unless sensitive data was redacted.",
        ),
        SelectionOption(
            "off",
            "Turn automatic recovery off",
            "Return the failed command result without asking a provider for a correction.",
        ),
    )
    selected = current if current in {"ask", "allow", "off"} else "ask"
    return select_interactively(
        "Choose recovery privacy",
        options,
        selected,
        settings,
        persisted_value=selected,
        allow_back=True,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def confirm_setup_cancel_interactively(
    settings: UXSettings,
    *,
    input_stream=None,
    output_stream=None,
) -> bool:
    """Confirm loss of the complete in-memory configuration draft once."""
    result = select_interactively(
        "Cancel configuration?",
        (
            SelectionOption(
                "continue",
                "Keep configuring (Recommended)",
                "Return to the current screen without discarding the draft.",
            ),
            SelectionOption(
                "cancel",
                "Cancel setup",
                "Discard every unsaved provider, model, credential, and recovery change.",
            ),
        ),
        "continue",
        settings,
        persisted_value="continue",
        allow_back=False,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    return result.action is SelectorAction.SELECT and result.value == "cancel"


def _select_setup_action(
    title: str,
    options: tuple[SelectionOption[str], ...],
    *,
    selected: str | None = None,
) -> str | None:
    """Use shared navigation in terminals and a stable fallback elsewhere."""
    if _native_selector_available():
        initial = selected or options[0].value
        result = select_interactively(
            title,
            options,
            initial,
            load_ux_settings(),
            persisted_value=initial,
            allow_back=True,
        )
        if result.action is SelectorAction.BACK:
            return "back"
        if result.action is SelectorAction.CANCEL:
            return None
        return result.value
    choice = questionary.select(
        title,
        choices=[
            questionary.Choice(option.label, value=option.value) for option in options
        ],
        style=ocean_theme,
    ).ask()
    return check_cancel(choice)


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
        choice = _select_setup_action(
            "The embedded Codex provider is required. What would you like to do?",
            (
                SelectionOption(
                    "install",
                    "Install now (Recommended)",
                    "Install the embedded Codex runtime, then continue setup.",
                ),
                SelectionOption("later", "Not now"),
                SelectionOption("back", "Back to model selection"),
            ),
        )
        if choice is None:
            return None
        if choice == "RETRY":
            continue
        if choice == "later":
            return "later"
        if choice == "back":
            return "back"
        if install_codex_sdk(console):
            return "ready"


def _offer_codex_login() -> None:
    """Offer Codex-managed sign-in after the provider is available."""
    if not _interactive_terminal() or not codex_sdk_installed():
        return

    from .codex_auth import login_codex_interactively

    login_codex_interactively(console, device_code=None)


ASSIGNMENT_PATTERN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


@dataclass(frozen=True)
class CredentialPlan:
    """A secret-bearing draft that performs no persistence until accepted."""

    provider: str
    source: Literal["keyring", "session", "legacy_session"]
    value: str | None = field(default=None, repr=False)


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


def _saved_recovery_preference(
    saved: dict[str, str | None],
    provider: str,
) -> str:
    global_preference = (saved.get("SHELLPA_RECOVERY_PERMISSION") or "").lower()
    if global_preference == "off":
        return "off"
    provider_name = (
        "SHELLPA_RECOVERY_PERMISSION_"
        + re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
    )
    if (saved.get(provider_name) or "").lower() == "allow":
        return "allow"
    return "ask"


def _select_legacy_action(backend_name: str, *, allow_session: bool) -> str | None:
    choices = [
        SelectionOption(
            "migrate",
            f"Move it to {backend_name} (Recommended)",
            "Remove the plaintext copy only after secure storage is verified.",
        ),
    ]
    if allow_session:
        choices.append(SelectionOption("session", "Use it for this ShellPa process"))
    choices.extend(
        [
            SelectionOption("remove", "Remove it and enter a new key"),
            SelectionOption("back", "Back to model selection"),
        ]
    )
    return _select_setup_action(
        "A legacy plaintext API key was found. What would you like to do?",
        tuple(choices),
    )


def _configure_api_credential(
    provider: str,
    env_path: Path,
    store: CredentialStore,
    *,
    allow_session: bool = True,
) -> CredentialPlan | Literal["back"] | None:
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
            choices: list[SelectionOption[str]] = []
            if allow_session:
                choices.append(
                    SelectionOption(
                        "session",
                        "Use the legacy key for this ShellPa process",
                    )
                )
            choices.extend(
                [
                    SelectionOption("remove", "Remove it and enter a new key"),
                    SelectionOption("back", "Back to model selection"),
                ]
            )
            action = _select_setup_action(
                "How should ShellPa continue?",
                tuple(choices),
            )

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
            return CredentialPlan(provider, "legacy_session", legacy_value)
        if action == "migrate":
            return CredentialPlan(provider, "keyring", legacy_value)

    saved_provider = (saved.get("SHELLPA_PROVIDER") or "").strip().lower()
    saved_source = (saved.get("SHELLPA_CREDENTIAL_STORE") or "").strip().lower()
    if saved_provider == provider and saved_source == "keyring" and backend.available:
        action = _select_setup_action(
            f"A {provider} credential is already stored securely.",
            (
                SelectionOption("keep", "Keep existing credential"),
                SelectionOption("replace", "Replace credential"),
                SelectionOption("remove", "Remove and replace credential"),
                SelectionOption("back", "Back to model selection"),
            ),
        )
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
                return CredentialPlan(provider, "keyring")

    if backend.available:
        console.print(f"[dim]Secure storage: {backend.name}[/dim]")
    else:
        console.print(f"[yellow]{backend.detail}[/yellow]")

    while True:
        if _native_selector_available():
            entered = prompt_input(
                f"Enter {PROVIDER_LABELS[provider]} API key",
                load_ux_settings(),
                description=(
                    f"The value will be stored in {backend.name}."
                    if backend.available
                    else "Secure persistence is unavailable; the value is hidden."
                ),
                secret=True,
            )
            if entered.action is InputAction.BACK:
                return "back"
            if entered.action is InputAction.CANCEL or entered.value is None:
                return None
            api_key = entered.value
        else:
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
            return CredentialPlan(provider, "keyring", api_key)

        session_choices: list[SelectionOption[str]] = []
        if allow_session:
            session_choices.append(
                SelectionOption(
                    "session",
                    "Use this key for this ShellPa process",
                )
            )
        session_choices.append(SelectionOption("back", "Back to model selection"))
        choice = _select_setup_action(
            "Secure persistence is unavailable.",
            tuple(session_choices),
        )
        if choice == "session":
            return CredentialPlan(provider, "session", api_key)
        if choice == "back":
            return "back"
        if choice is None:
            return None


def _apply_credential_plan(
    plan: CredentialPlan,
    store: CredentialStore,
) -> Literal["keyring", "session", "legacy_session"] | None:
    """Apply a reviewed credential draft without exposing its value."""
    if plan.source in {"session", "legacy_session"}:
        if plan.value is None:
            return None
        set_session_credential(plan.provider, plan.value)
        return plan.source
    if plan.value is None:
        return "keyring"
    try:
        store.set(plan.provider, plan.value)
        if store.get(plan.provider) != plan.value.strip():
            raise CredentialStoreError("Credential verification failed.")
    except CredentialStoreError as exc:
        console.print(f"[red]{exc} Configuration was not saved.[/red]")
        return None
    console.print(
        f"[green]{MICRO_MARK} Credential stored in {store.status().name}; "
        "plaintext copy removed.[/green]"
    )
    return "keyring"


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


def _review_configuration_draft(
    provider: str,
    model: str,
    credential_plan: CredentialPlan | None,
    recovery_preference: str | None,
) -> Literal["save", "back", "cancel"]:
    """Show a redacted final review before any draft is persisted."""
    credential_label = (
        "Managed by Codex"
        if provider == "codex"
        else "Stored securely"
        if credential_plan is not None and credential_plan.source == "keyring"
        else "Current process only"
    )
    recovery_label = {
        "ask": "Ask before recovery",
        "allow": f"Allow minimal recovery for {provider}",
        "off": "Automatic recovery off",
        None: "Use existing preference",
    }[recovery_preference]
    console.print("\n[bold]Review configuration[/bold]")
    console.print(f"[dim]Provider[/dim]    {provider}")
    console.print(f"[dim]Model[/dim]       {model}")
    console.print(f"[dim]Credential[/dim]  {credential_label}")
    console.print(f"[dim]Recovery[/dim]    {recovery_label}\n")
    if _native_selector_available():
        result = select_interactively(
            "Apply this configuration?",
            (
                SelectionOption("save", "Save configuration"),
                SelectionOption("back", "Back to recovery preference"),
                SelectionOption("cancel", "Cancel setup"),
            ),
            "save",
            load_ux_settings(),
            allow_back=True,
        )
        if result.action is SelectorAction.BACK:
            return "back"
        if result.action is SelectorAction.CANCEL:
            return "cancel"
        if result.value == "save":
            return "save"
        if result.value == "back":
            return "back"
        return "cancel"
    choice = questionary.select(
        "Apply this configuration?",
        choices=[
            questionary.Choice("Save configuration", value="save"),
            questionary.Choice("Back to recovery preference", value="back"),
            questionary.Choice("Cancel setup", value="cancel"),
        ],
        style=ocean_theme,
    ).ask()
    choice = check_cancel(choice)
    return choice if choice in {"save", "back"} else "cancel"


def _choose_provider(
    current: str,
    settings: UXSettings,
) -> SelectorResult[str]:
    if _native_selector_available():
        return select_provider_interactively(current, settings)
    while True:
        value = questionary.select(
            "Select your AI Provider:",
            choices=[
                questionary.Choice(
                    f"{provider_icon(provider)} {PROVIDER_LABELS[provider]}"
                    + (" (Recommended)" if provider == "openrouter" else ""),
                    value=provider,
                )
                for provider in PROVIDER_ORDER
            ],
            style=ocean_theme,
        ).ask()
        value = check_cancel(value)
        if value == "RETRY":
            continue
        if value is None:
            return SelectorResult(SelectorAction.CANCEL)
        return SelectorResult(SelectorAction.SELECT, value)


def _choose_model(
    provider: str,
    current: str | None,
    settings: UXSettings,
) -> SelectorResult[str]:
    if _native_selector_available():
        return select_model_interactively(provider, current, settings)
    while True:
        model_choices: list[questionary.Choice | str] = list(PROVIDER_MODELS[provider])
        model_choices.append(questionary.Choice("Custom Model...", value="custom"))
        value = questionary.select(
            "Select the model:", choices=model_choices, style=ocean_theme
        ).ask()
        value = check_cancel(value)
        if value == "RETRY":
            continue
        if value is None:
            return SelectorResult(SelectorAction.CANCEL)
        if value != "custom":
            return SelectorResult(SelectorAction.SELECT, value)
        while True:
            custom = questionary.text(
                "Enter your custom model string (e.g. ollama/mistral):",
                style=ocean_theme,
            ).ask()
            custom = check_cancel(custom)
            if custom == "RETRY":
                continue
            if custom is None:
                return SelectorResult(SelectorAction.CANCEL)
            return SelectorResult(SelectorAction.SELECT, custom)


def _choose_recovery(
    provider: str,
    current: str,
    settings: UXSettings,
) -> SelectorResult[str]:
    if _native_selector_available():
        return select_recovery_interactively(provider, current, settings)
    if not _interactive_terminal():
        return SelectorResult(SelectorAction.SELECT, current)
    while True:
        value = _select_recovery_preference(provider)
        if value == "RETRY":
            continue
        if value is None:
            return SelectorResult(SelectorAction.CANCEL)
        return SelectorResult(SelectorAction.SELECT, value)


def run_setup_wizard(
    store: CredentialStore | None = None,
    *,
    allow_session: bool = True,
) -> SetupOutcome:
    credential_store = store or CredentialStore()
    settings = load_ux_settings()
    env_path = get_env_path()
    saved = _saved_config(env_path)
    saved_provider = (saved.get("SHELLPA_PROVIDER") or "").strip().lower()
    saved_model = (saved.get("SHELLPA_MODEL") or "").strip() or None
    console.print()
    console.print(
        brand_logo_text(
            settings,
            width=console.width,
        )
    )
    console.print()

    console.print("[bold cyan]Configure ShellPa[/bold cyan]")
    console.print("[dim]Choose your provider, model, and privacy preferences.[/dim]\n")

    provider = saved_provider if saved_provider in PROVIDER_ORDER else PROVIDER_ORDER[0]
    model = saved_model if saved_provider == provider else None
    credential_plan: CredentialPlan | None = None
    recovery_preference = _saved_recovery_preference(saved, provider)
    step: Literal["provider", "model", "credential", "recovery", "review"] = "provider"

    while True:
        if step == "provider":
            result = _choose_provider(provider, settings)
            if result.action is not SelectorAction.SELECT or result.value is None:
                if (
                    _native_selector_available()
                    and not confirm_setup_cancel_interactively(settings)
                ):
                    continue
                return SetupOutcome.CANCELLED
            previous_provider = provider
            provider = result.value
            if provider != previous_provider:
                model = saved_model if provider == saved_provider else None
                credential_plan = None
                recovery_preference = _saved_recovery_preference(saved, provider)
            step = "model"
            continue

        if step == "model":
            result = _choose_model(provider, model, settings)
            if result.action is SelectorAction.BACK:
                step = "provider"
                continue
            if result.action is SelectorAction.CANCEL or result.value is None:
                if (
                    _native_selector_available()
                    and not confirm_setup_cancel_interactively(settings)
                ):
                    continue
                return SetupOutcome.CANCELLED
            model = result.value
            credential_plan = None
            step = "credential"
            continue

        if step == "credential":
            if provider == "codex":
                codex_state = _prepare_codex_provider()
                if codex_state is None:
                    if (
                        _native_selector_available()
                        and not confirm_setup_cancel_interactively(settings)
                    ):
                        continue
                    return SetupOutcome.CANCELLED
                if codex_state == "back":
                    step = "model"
                    continue
                credential_plan = None
            else:
                credential_result = _configure_api_credential(
                    provider,
                    env_path,
                    credential_store,
                    allow_session=allow_session,
                )
                if credential_result is None:
                    if (
                        _native_selector_available()
                        and not confirm_setup_cancel_interactively(settings)
                    ):
                        continue
                    return SetupOutcome.CANCELLED
                if credential_result == "back":
                    step = "model"
                    continue
                credential_plan = credential_result
            step = "recovery"
            continue

        if step == "recovery":
            result = _choose_recovery(provider, recovery_preference, settings)
            if result.action is SelectorAction.BACK:
                step = "credential"
                continue
            if result.action is SelectorAction.CANCEL or result.value is None:
                if (
                    _native_selector_available()
                    and not confirm_setup_cancel_interactively(settings)
                ):
                    continue
                return SetupOutcome.CANCELLED
            recovery_preference = result.value
            if not _interactive_terminal():
                break
            step = "review"
            continue

        review_action = _review_configuration_draft(
            provider,
            model or "",
            credential_plan,
            recovery_preference,
        )
        if review_action == "back":
            step = "recovery"
            continue
        if review_action == "cancel":
            console.print(
                "[yellow]Configuration cancelled. Nothing was saved.[/yellow]"
            )
            return SetupOutcome.CANCELLED
        break

    if model is None:
        return SetupOutcome.FAILED

    credential_source: str | None = None
    if credential_plan is not None:
        credential_source = _apply_credential_plan(
            credential_plan,
            credential_store,
        )
        if credential_source is None:
            return SetupOutcome.FAILED
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

    console.print(f"\n[bold green]{MICRO_MARK} Configuration saved.[/bold green]")
    if provider == "codex":
        if codex_sdk_installed():
            _offer_codex_login()
        else:
            command = format_command(codex_install_command())
            console.print(f"[cyan]When you are ready, run: {command}[/cyan]")
            console.print("[dim]Then start sign-in with: shellpa login[/dim]")
    return SetupOutcome.SAVED
