"""Build privacy-conscious context for command recovery."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .executor import result_error_message
from .models import ExecutionRequest, ExecutionResult, RecoveryContext

SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD))\s*=\s*"
        r"([^\s;&]+)"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|"
        r"github_pat_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9_-]{8,})\b"
    ),
    re.compile(r"(https?://[^/\s:@]+:)[^@\s/]+@"),
)
MAX_PROVIDER_ERROR_CHARS = 2_000


class RecoveryPermission(str, Enum):
    ASK = "ask"
    ALLOW = "allow"
    OFF = "off"


def redact_sensitive_text(text: str) -> str:
    """Redact common secret shapes without destroying diagnostic structure."""
    redacted = text
    redacted = SECRET_PATTERNS[0].sub(
        lambda match: f"{match.group(1)}=<REDACTED>", redacted
    )
    redacted = SECRET_PATTERNS[1].sub("Bearer <REDACTED>", redacted)
    redacted = SECRET_PATTERNS[2].sub("<REDACTED_TOKEN>", redacted)
    redacted = SECRET_PATTERNS[3].sub(r"\1<REDACTED>@", redacted)

    home = str(Path.home())
    if home:
        redacted = redacted.replace(home, "~")
        redacted = redacted.replace(home.replace("\\", "/"), "~")
    return redacted


def configured_recovery_permission(
    provider: str = "",
    environ: dict[str, str] | None = None,
) -> RecoveryPermission:
    import os

    values = os.environ if environ is None else environ
    provider_key = _provider_permission_key(provider)
    global_value = (values.get("SHELLPA_RECOVERY_PERMISSION") or "").strip().lower()
    if global_value == RecoveryPermission.OFF.value:
        return RecoveryPermission.OFF
    raw = (values.get(provider_key) or global_value or "ask").strip().lower()
    try:
        return RecoveryPermission(raw)
    except ValueError:
        return RecoveryPermission.ASK


def _provider_permission_key(provider: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider.strip()).strip("_")
    return f"SHELLPA_RECOVERY_PERMISSION_{normalized.upper() or 'DEFAULT'}"


def _save_recovery_permission(
    permission: RecoveryPermission,
    provider: str,
) -> None:
    import os

    from .setup import _update_config_file, get_env_path

    name = (
        "SHELLPA_RECOVERY_PERMISSION"
        if permission is RecoveryPermission.OFF
        else _provider_permission_key(provider)
    )
    _update_config_file(get_env_path(), {name: permission.value})
    os.environ[name] = permission.value


def format_recovery_disclosure(context: RecoveryContext) -> str:
    """Render the exact minimal, redacted facts used for correction."""
    return (
        f"Original request: {context.original_query}\n"
        f"Failed command: {context.failed_command}\n"
        f"Exit status: {context.exit_code}\n"
        f"Timed out: {context.timed_out}\n"
        f"Error summary: {context.error_message}"
    )


def request_recovery_permission(
    console: Console,
    context: RecoveryContext,
    provider: str,
    *,
    style: Any = None,
    interactive: bool | None = None,
) -> bool:
    """Authorize one bounded corrective provider request without telemetry."""
    permission = configured_recovery_permission(provider)
    if permission is RecoveryPermission.OFF:
        return False
    if permission is RecoveryPermission.ALLOW and not context.sensitive_data_redacted:
        return True

    can_prompt = console.is_terminal if interactive is None else interactive
    if not can_prompt:
        console.print(
            "[yellow]Automatic recovery skipped because permission cannot be "
            "requested in this terminal.[/yellow]"
        )
        return False

    while True:
        choice = questionary.select(
            (
                "The command failed. ShellPa can ask "
                f"{provider or 'the selected provider'} for a corrected command "
                "using minimal, redacted failure details."
            ),
            choices=[
                questionary.Choice("Continue this time", value="once"),
                questionary.Choice(
                    "Always allow minimal recovery for this provider",
                    value="always",
                ),
                questionary.Choice("View the exact redacted information", value="view"),
                questionary.Choice("Stop this recovery", value="stop"),
                questionary.Choice("Turn off automatic recovery", value="off"),
            ],
            style=style,
        ).ask()
        if choice == "view":
            console.print(
                Panel(
                    Text(format_recovery_disclosure(context)),
                    title="Provider-safe recovery information",
                    border_style="cyan",
                )
            )
            continue
        if choice == "once":
            return True
        if choice == "always":
            _save_recovery_permission(RecoveryPermission.ALLOW, provider)
            return True
        if choice == "off":
            _save_recovery_permission(RecoveryPermission.OFF, provider)
        return False


def build_recovery_context(
    original_query: str,
    request: ExecutionRequest,
    result: ExecutionResult,
) -> RecoveryContext:
    """Create redacted, structured facts for a correction request."""
    original_query_redacted = redact_sensitive_text(original_query)
    failed_command_redacted = redact_sensitive_text(request.command)
    raw_error = result_error_message(result)
    error_redacted = redact_sensitive_text(raw_error)
    if len(error_redacted) > MAX_PROVIDER_ERROR_CHARS:
        error_redacted = error_redacted[-MAX_PROVIDER_ERROR_CHARS:]
    return RecoveryContext(
        original_query=original_query_redacted,
        failed_command=failed_command_redacted,
        error_message=error_redacted,
        exit_code=result.exit_code,
        attempt=request.attempt,
        timed_out=result.timed_out,
        cancelled=result.cancelled,
        output_truncated=result.output_truncated,
        partial_effect_possible=result.partial_effect_possible,
        sensitive_data_redacted=(
            original_query_redacted != original_query
            or failed_command_redacted != request.command
            or error_redacted != raw_error
        ),
    )
