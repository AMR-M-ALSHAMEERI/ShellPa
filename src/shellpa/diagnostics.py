"""Secret-free local diagnostics for ShellPa installations."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .codex_provider import (
    CODEX_EXTRA_INSTALL,
    CodexAccountState,
    inspect_codex_account,
)
from .config import (
    ConfigStatus,
    inspect_config,
    load_environment_sources,
)
from .credentials import inspect_credential_backend
from .icons import unicode_icons_supported
from .os_detect import detect_environment
from .setup import get_env_path
from .ux import get_settings_path


class CheckLevel(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    level: CheckLevel
    detail: str
    remedy: str = ""


@dataclass
class DoctorReport:
    checks: list[DiagnosticCheck]

    @property
    def exit_code(self) -> int:
        return 1 if any(check.level is CheckLevel.FAIL for check in self.checks) else 0


PROVIDER_HOSTS = {
    "openrouter": "https://openrouter.ai",
    "openai": "https://api.openai.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "anthropic": "https://api.anthropic.com",
    "codex": "https://chatgpt.com",
}

REQUIRED_MODULES = (
    "typer",
    "rich",
    "litellm",
    "pydantic",
    "dotenv",
    "keyring",
    "questionary",
    "prompt_toolkit",
)


def _check(
    name: str,
    condition: bool,
    pass_detail: str,
    fail_detail: str,
    *,
    fail_level: CheckLevel = CheckLevel.FAIL,
    remedy: str = "",
) -> DiagnosticCheck:
    return DiagnosticCheck(
        name,
        CheckLevel.PASS if condition else fail_level,
        pass_detail if condition else fail_detail,
        "" if condition else remedy,
    )


def _writable_parent(path: Path) -> bool:
    candidate = path
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate.exists() and os.access(candidate, os.W_OK)


def _configuration_checks(status: ConfigStatus) -> list[DiagnosticCheck]:
    provider_detail = status.provider or "custom or unknown provider"
    if status.provider == "codex":
        credential_check = DiagnosticCheck(
            "Credential",
            CheckLevel.PASS,
            "Managed by the official Codex SDK; value unavailable to ShellPa.",
        )
    else:
        source_labels = {
            "keyring": "stored securely (value hidden)",
            "environment": "provided by the current environment (value hidden)",
            "session": "available for this process only (value hidden)",
        }
        detail = source_labels.get(
            status.credential_source or "",
            f"{status.api_key_name or 'provider credential'} is missing or empty.",
        )
        credential_check = _check(
            "Credential",
            status.api_key_configured,
            detail,
            detail,
            remedy="Run: shellpa config",
        )
    return [
        _check(
            "Model",
            status.model_configured,
            status.model_name or "configured",
            "No model is configured.",
            remedy="Run: shellpa config",
        ),
        _check(
            "Provider",
            status.provider is not None,
            provider_detail,
            provider_detail,
            fail_level=CheckLevel.WARN,
            remedy="Save a supported provider with: shellpa config",
        ),
        credential_check,
    ]


def _codex_checks() -> list[DiagnosticCheck]:
    status = inspect_codex_account()
    if status.state is CodexAccountState.UNAVAILABLE:
        return [
            DiagnosticCheck(
                "Codex SDK",
                CheckLevel.FAIL,
                "The optional embedded Codex runtime is not installed.",
                f"Run: {CODEX_EXTRA_INSTALL}",
            )
        ]

    checks = [
        DiagnosticCheck(
            "Codex SDK",
            CheckLevel.PASS,
            "The embedded Codex SDK and pinned runtime are importable.",
        )
    ]
    if status.state is CodexAccountState.CHATGPT:
        plan = f" ({status.plan_type})" if status.plan_type else ""
        checks.append(
            DiagnosticCheck(
                "Codex account",
                CheckLevel.PASS,
                f"ChatGPT account connected{plan}; identity hidden.",
            )
        )
    elif status.state in {
        CodexAccountState.SIGNED_OUT,
        CodexAccountState.OTHER,
    }:
        checks.append(
            DiagnosticCheck(
                "Codex account",
                CheckLevel.FAIL,
                status.detail,
                "Run: shellpa login",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                "Codex account",
                CheckLevel.FAIL,
                status.detail,
                "Check the Codex runtime, then run: shellpa login",
            )
        )
    return checks


def _credential_storage_check() -> DiagnosticCheck:
    status = inspect_credential_backend()
    return DiagnosticCheck(
        "Credential storage",
        CheckLevel.PASS if status.available else CheckLevel.FAIL,
        status.detail,
        (
            ""
            if status.available
            else "Configure an operating-system credential service or use a session-only key."
        ),
    )


def _online_check(
    provider: str | None,
    *,
    opener: Callable = urllib.request.urlopen,
) -> DiagnosticCheck:
    endpoint = PROVIDER_HOSTS.get(provider or "")
    if endpoint is None:
        return DiagnosticCheck(
            "Provider reachability",
            CheckLevel.WARN,
            "No standard endpoint is known for this provider.",
            "Verify the custom provider manually.",
        )
    request = urllib.request.Request(
        endpoint,
        method="HEAD",
        headers={"User-Agent": f"ShellPa/{__version__}"},
    )
    try:
        response = opener(request, timeout=5)
        close = getattr(response, "close", None)
        if close is not None:
            close()
        return DiagnosticCheck(
            "Provider reachability",
            CheckLevel.PASS,
            f"{endpoint} is reachable; no model request was sent.",
        )
    except urllib.error.HTTPError as exc:
        # Any HTTP response proves the host was reached. No credential is sent.
        return DiagnosticCheck(
            "Provider reachability",
            CheckLevel.PASS,
            f"{endpoint} responded with HTTP {exc.code}; no credential was sent.",
        )
    except (urllib.error.URLError, OSError) as exc:
        return DiagnosticCheck(
            "Provider reachability",
            CheckLevel.FAIL,
            f"{endpoint} could not be reached: {exc}",
            "Check DNS, firewall, proxy, and internet access.",
        )


def run_doctor(
    *,
    online: bool = False,
    environ: dict[str, str] | None = None,
    opener: Callable = urllib.request.urlopen,
) -> DoctorReport:
    if environ is None:
        load_environment_sources()
    values = os.environ if environ is None else environ
    status = inspect_config(values)
    environment = detect_environment()
    python_supported = sys.version_info >= (3, 10)
    in_virtualenv = sys.prefix != sys.base_prefix
    shell = environment["shell"]
    shell_program = {
        "powershell": "powershell.exe",
        "pwsh": "pwsh",
        "cmd": "cmd.exe",
    }.get(shell, shell)

    checks = [
        DiagnosticCheck("ShellPa", CheckLevel.PASS, f"version {__version__}"),
        _check(
            "Python",
            python_supported,
            f"{sys.version.split()[0]} is supported.",
            f"{sys.version.split()[0]} is unsupported.",
            remedy="Install Python 3.10 or newer.",
        ),
        DiagnosticCheck(
            "Python runtime",
            CheckLevel.PASS,
            "isolated environment" if in_virtualenv else "system environment",
        ),
        DiagnosticCheck(
            "Operating system",
            CheckLevel.PASS,
            str(environment["os"]),
        ),
        _check(
            "Detected shell",
            bool(shutil.which(shell_program)),
            f"{shell} ({shutil.which(shell_program)})",
            f"{shell} executable was not found on PATH.",
            fail_level=CheckLevel.WARN,
            remedy="Use a supported shell or correct PATH.",
        ),
        *_configuration_checks(status),
        *(
            [_credential_storage_check()]
            if status.credential_source == "keyring"
            else []
        ),
        *(_codex_checks() if status.provider == "codex" else []),
        _check(
            "Git",
            bool(shutil.which("git")),
            shutil.which("git") or "available",
            "Git was not found on PATH.",
            fail_level=CheckLevel.WARN,
            remedy="Install Git if repository-aware features are needed.",
        ),
        DiagnosticCheck(
            "Terminal",
            CheckLevel.PASS if sys.stdout.isatty() else CheckLevel.WARN,
            (
                "interactive"
                if sys.stdout.isatty()
                else "output is redirected; animation and menus use fallbacks"
            ),
        ),
        DiagnosticCheck(
            "Unicode icons",
            CheckLevel.PASS if unicode_icons_supported() else CheckLevel.WARN,
            "supported" if unicode_icons_supported() else "using ASCII fallback",
        ),
        _check(
            "Configuration location",
            _writable_parent(get_env_path()),
            f"{get_env_path()} is writable.",
            f"{get_env_path()} is not writable.",
            remedy="Check user-directory permissions.",
        ),
        _check(
            "Settings location",
            _writable_parent(get_settings_path()),
            f"{get_settings_path()} is writable.",
            f"{get_settings_path()} is not writable.",
            remedy="Check user-directory permissions.",
        ),
    ]

    missing_modules = [
        module
        for module in REQUIRED_MODULES
        if importlib.util.find_spec(module) is None
    ]
    checks.append(
        _check(
            "Dependencies",
            not missing_modules,
            "All required Python modules are importable.",
            "Missing modules: " + ", ".join(missing_modules),
            remedy="Run: python -m pip install -e .",
        )
    )
    if online:
        checks.append(_online_check(status.provider, opener=opener))
    return DoctorReport(checks)


def display_doctor(console: Console, report: DoctorReport) -> None:
    colors = {
        CheckLevel.PASS: "green",
        CheckLevel.WARN: "yellow",
        CheckLevel.FAIL: "red",
    }
    table = Table(title="ShellPa doctor", expand=True)
    table.add_column("Check", style="bold")
    table.add_column("Status", width=6)
    table.add_column("Detail", overflow="fold")
    table.add_column("Suggested action", overflow="fold")
    for check in report.checks:
        table.add_row(
            check.name,
            f"[{colors[check.level]}]{check.level.value}[/]",
            check.detail,
            check.remedy,
        )
    console.print(table)
    if report.exit_code:
        console.print("[red]Doctor found one or more blocking problems.[/red]")
    elif any(check.level is CheckLevel.WARN for check in report.checks):
        console.print("[yellow]Doctor completed with warnings.[/yellow]")
    else:
        console.print("[green]Doctor completed successfully.[/green]")
