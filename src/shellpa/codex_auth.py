"""Interactive ChatGPT authentication delegated to the official Codex SDK."""

from __future__ import annotations

import tempfile
import webbrowser
from collections.abc import Callable

from rich.console import Console

from .codex_provider import CodexProviderError, _client_config, _load_sdk
from .recovery import redact_sensitive_text


def login_codex(
    console: Console,
    *,
    device_code: bool = False,
    opener: Callable[[str], object] = webbrowser.open,
) -> bool:
    """Start a Codex-managed ChatGPT login without handling credentials."""
    try:
        sdk = _load_sdk()
    except CodexProviderError as exc:
        console.print(f"[red]{exc}[/red]")
        return False

    try:
        with tempfile.TemporaryDirectory(prefix="shellpa-codex-login-") as temp_dir:
            with sdk.Codex(config=_client_config(sdk, temp_dir)) as codex:
                if device_code:
                    login = codex.login_chatgpt_device_code()
                    console.print(
                        "[bold cyan]Open this address in your browser:[/bold cyan] "
                        f"{login.verification_url}"
                    )
                    console.print(
                        "[bold cyan]Enter this one-time code:[/bold cyan] "
                        f"{login.user_code}"
                    )
                else:
                    login = codex.login_chatgpt()
                    console.print(
                        "[bold cyan]Opening the official ChatGPT sign-in page...[/bold cyan]"
                    )
                    console.print(f"[dim]{login.auth_url}[/dim]")
                    opener(login.auth_url)

                console.print("[dim]Waiting for Codex to confirm sign-in...[/dim]")
                try:
                    completed = login.wait()
                except KeyboardInterrupt:
                    login.cancel()
                    console.print("[yellow]ChatGPT sign-in cancelled.[/yellow]")
                    return False
    except Exception as exc:
        console.print(
            f"[red]ChatGPT sign-in failed through Codex: {type(exc).__name__}.[/red]"
        )
        return False

    if not bool(getattr(completed, "success", False)):
        error = redact_sensitive_text(
            str(getattr(completed, "error", None) or "Codex did not complete sign-in.")
        )
        console.print(f"[red]{error}[/red]")
        return False
    console.print(
        "[green]Your ChatGPT account is ready to use with ShellPa through Codex. "
        "Your sign-in session is managed by Codex, not ShellPa.[/green]"
    )
    return True


def logout_codex(console: Console) -> bool:
    """Ask Codex to remove its managed account session."""
    try:
        sdk = _load_sdk()
    except CodexProviderError as exc:
        console.print(f"[red]{exc}[/red]")
        return False

    try:
        with tempfile.TemporaryDirectory(prefix="shellpa-codex-logout-") as temp_dir:
            with sdk.Codex(config=_client_config(sdk, temp_dir)) as codex:
                codex.logout()
    except Exception as exc:
        console.print(f"[red]Codex sign-out failed: {type(exc).__name__}.[/red]")
        return False
    console.print("[green]Codex has signed out of the ChatGPT account.[/green]")
    return True
