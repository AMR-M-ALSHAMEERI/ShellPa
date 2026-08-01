import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values, find_dotenv
from pydantic import BaseModel
from rich.console import Console

from .credentials import (
    PROVIDER_API_KEYS,
    has_session_credential,
    set_session_credential,
)
from .setup import SetupOutcome, get_env_path, run_setup_wizard

console = Console()

SUPPORTED_PROVIDERS = frozenset((*PROVIDER_API_KEYS, "codex"))
CONFIG_METADATA_KEYS = frozenset(
    {
        "SHELLPA_MODEL",
        "SHELLPA_PROVIDER",
        "SHELLPA_CREDENTIAL_STORE",
        "SHELLPA_RECOVERY_PERMISSION",
    }
)


class ConfigStatus(BaseModel):
    """A secret-free summary of ShellPa's current configuration."""

    model_name: str | None
    provider: str | None
    api_key_name: str | None
    model_configured: bool
    api_key_configured: bool
    credential_source: str | None = None

    @property
    def is_configured(self) -> bool:
        credential_ready = self.api_key_configured or self.provider == "codex"
        return self.model_configured and credential_ready


def infer_provider(
    model_name: str | None, explicit_provider: str | None = None
) -> str | None:
    """Infer a supported provider while preferring an explicit saved choice."""
    if explicit_provider:
        normalized_provider = explicit_provider.strip().lower()
        if normalized_provider in SUPPORTED_PROVIDERS:
            return normalized_provider

    normalized_model = (model_name or "").strip().lower()
    if normalized_model.startswith("openrouter/"):
        return "openrouter"
    if normalized_model.startswith("codex/"):
        return "codex"
    if normalized_model.startswith(("gemini/", "gemini-")):
        return "gemini"
    if normalized_model.startswith(("anthropic/", "claude-")):
        return "anthropic"
    if normalized_model.startswith(("openai/", "gpt-", "o1", "o3", "o4")):
        return "openai"
    return None


def inspect_config(environ: Mapping[str, str] | None = None) -> ConfigStatus:
    """Return configuration readiness without exposing any credential values."""
    values = os.environ if environ is None else environ
    model_name = (values.get("SHELLPA_MODEL") or "").strip() or None
    provider = infer_provider(model_name, values.get("SHELLPA_PROVIDER"))
    api_key_name = PROVIDER_API_KEYS.get(provider) if provider else None
    declared_source = (values.get("SHELLPA_CREDENTIAL_STORE") or "").strip().lower()
    credential_source: str | None = None

    if provider and has_session_credential(provider):
        api_key_configured = True
        credential_source = "session"
    elif api_key_name and (values.get(api_key_name) or "").strip():
        api_key_configured = True
        credential_source = "environment"
    elif api_key_name and declared_source == "keyring":
        # Configuration status intentionally trusts the non-secret marker. The
        # credential itself is retrieved only when the provider is called.
        api_key_configured = True
        credential_source = "keyring"
    elif api_key_name:
        api_key_configured = False
    else:
        # Backward compatibility for custom models saved before provider metadata.
        api_key_configured = any(
            bool((values.get(key_name) or "").strip())
            for key_name in PROVIDER_API_KEYS.values()
        )

    return ConfigStatus(
        model_name=model_name,
        provider=provider,
        api_key_name=api_key_name,
        model_configured=model_name is not None,
        api_key_configured=api_key_configured,
        credential_source=credential_source,
    )


def _load_metadata_file(path: Path) -> dict[str, str | None]:
    if not path.is_file():
        return {}
    values = dotenv_values(path)
    metadata_names = {
        name
        for name in values
        if name in CONFIG_METADATA_KEYS
        or name.startswith("SHELLPA_RECOVERY_PERMISSION_")
    }
    for name in metadata_names:
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            os.environ.setdefault(name, value.strip())
    return dict(values)


def load_environment_sources() -> None:
    """Load non-secret project and user metadata without importing API keys."""
    local_env = find_dotenv(usecwd=True)
    if local_env:
        local_values = _load_metadata_file(Path(local_env))
        model = (local_values.get("SHELLPA_MODEL") or "").strip()
        provider = infer_provider(model, local_values.get("SHELLPA_PROVIDER"))
        key_name = PROVIDER_API_KEYS.get(provider or "")
        local_credential = local_values.get(key_name or "")
        if provider and isinstance(local_credential, str) and local_credential.strip():
            # A project-managed .env remains compatible, but its key is held in
            # memory rather than imported into the process environment.
            set_session_credential(provider, local_credential)
    env_path = get_env_path()
    _load_metadata_file(env_path)


def load_config() -> ConfigStatus:
    """Load config from local .env or global ~/.shellpa.env file."""
    load_environment_sources()

    status = inspect_config()
    if not status.is_configured:
        console.print("[yellow]Initial configuration required...[/yellow]")
        outcome = run_setup_wizard()
        if outcome is not SetupOutcome.SAVED:
            console.print(
                "[bold red]Error: You must configure ShellPa before using it.[/bold red]"
            )
            raise SystemExit(1)
        status = inspect_config()
        if not status.is_configured:
            console.print(
                "[bold red]Error: The selected provider requires a non-empty API key.[/bold red]"
            )
            raise SystemExit(1)

    return status
