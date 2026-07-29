import os
from collections.abc import Mapping

from dotenv import load_dotenv
from pydantic import BaseModel
from rich.console import Console

from .setup import get_env_path, run_setup_wizard

console = Console()

PROVIDER_API_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
SUPPORTED_PROVIDERS = frozenset((*PROVIDER_API_KEYS, "codex"))


class ConfigStatus(BaseModel):
    """A secret-free summary of ShellPa's current configuration."""

    model_name: str | None
    provider: str | None
    api_key_name: str | None
    model_configured: bool
    api_key_configured: bool

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

    if api_key_name:
        api_key_configured = bool((values.get(api_key_name) or "").strip())
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
    )


def load_environment_sources() -> None:
    """Load project and user configuration without starting the setup wizard."""
    load_dotenv()
    env_path = get_env_path()
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)


def load_config() -> ConfigStatus:
    """Load config from local .env or global ~/.shellpa.env file."""
    load_environment_sources()

    status = inspect_config()
    if not status.is_configured:
        console.print("[yellow]Initial configuration required...[/yellow]")
        success = run_setup_wizard()
        if not success:
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
