"""Interactive ChatGPT authentication delegated to the official Codex SDK."""

from __future__ import annotations

import sys
import tempfile
import webbrowser
from collections.abc import Callable

import questionary
from rich.console import Console
from rich.markup import escape

from .codex_provider import (
    CodexAccountState,
    CodexAccountStatus,
    CodexProviderError,
    _client_config,
    _load_sdk,
    inspect_codex_account,
)
from .recovery import redact_sensitive_text

auth_theme = questionary.Style(
    [
        ("qmark", "fg:#00ffff bold"),
        ("question", "fg:#ffffff bold"),
        ("answer", "fg:#00ccff bold"),
        ("pointer", "fg:#00ffff bold"),
        ("highlighted", "fg:#0055ff bold"),
        ("instruction", "fg:#0077ff"),
    ]
)


def _interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _select(prompt: str, choices: list[questionary.Choice]) -> str | None:
    return questionary.select(prompt, choices=choices, style=auth_theme).ask()


def _display_connected_status(
    console: Console,
    status: CodexAccountStatus,
) -> None:
    plan = f" — {escape(status.plan_type)}" if status.plan_type else ""
    console.print(
        f"[green]A ChatGPT account is already connected through Codex{plan}.[/green]"
    )


def _inspect_account_with_status(console: Console) -> CodexAccountStatus:
    with console.status(
        "[cyan]Checking the Codex account session...[/cyan]",
        spinner="dots",
    ):
        return inspect_codex_account()


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


def login_codex_interactively(
    console: Console,
    *,
    device_code: bool | None = False,
    account_status: CodexAccountStatus | None = None,
) -> bool:
    """Guard login with account status and safe interactive choices."""
    status = account_status or _inspect_account_with_status(console)
    if status.state is CodexAccountState.CHATGPT:
        _display_connected_status(console, status)
        if not _interactive_terminal():
            console.print("[dim]The current Codex session was kept unchanged.[/dim]")
            return True
        action = _select(
            "What would you like to do?",
            [
                questionary.Choice(
                    "Keep current session (Recommended)",
                    value="keep",
                ),
                questionary.Choice(
                    "Sign in again or switch account",
                    value="switch",
                ),
                questionary.Choice("Cancel", value="cancel"),
            ],
        )
        if action == "keep":
            console.print("[dim]The current Codex session was kept.[/dim]")
            return True
        if action is None or action == "cancel":
            console.print("[yellow]ChatGPT sign-in cancelled.[/yellow]")
            return True

    if device_code is None:
        if not _interactive_terminal():
            console.print(
                "[yellow]Interactive ChatGPT sign-in requires a terminal.[/yellow]"
            )
            return False
        method = _select(
            "Choose a ChatGPT sign-in method:",
            [
                questionary.Choice(
                    "Sign in with browser (Recommended)",
                    value="browser",
                ),
                questionary.Choice("Sign in with device code", value="device"),
                questionary.Choice("Later", value="later"),
            ],
        )
        if method is None or method == "later":
            console.print("[dim]ChatGPT sign-in was left for later.[/dim]")
            return True
        device_code = method == "device"

    return login_codex(console, device_code=device_code)


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


def logout_codex_interactively(
    console: Console,
    *,
    account_status: CodexAccountStatus | None = None,
) -> bool:
    """Require explicit interactive approval before clearing Codex credentials."""
    status = account_status or _inspect_account_with_status(console)
    if status.state is CodexAccountState.SIGNED_OUT:
        console.print("[dim]Codex is already signed out of ChatGPT.[/dim]")
        return True
    if status.state is CodexAccountState.UNAVAILABLE:
        console.print(f"[red]{status.detail}[/red]")
        return False
    if not _interactive_terminal():
        console.print(
            "[yellow]Codex sign-out requires confirmation in an interactive "
            "terminal.[/yellow]"
        )
        return False

    if status.state is CodexAccountState.CHATGPT:
        _display_connected_status(console, status)
    elif status.state is CodexAccountState.OTHER:
        console.print("[yellow]Codex is using a non-ChatGPT session.[/yellow]")
    elif status.state is CodexAccountState.ERROR:
        console.print(f"[yellow]{status.detail}[/yellow]")
    action = _select(
        "Clear the current Codex-managed account session?",
        [
            questionary.Choice(
                "Keep current session (Recommended)",
                value="keep",
            ),
            questionary.Choice("Sign out of Codex", value="logout"),
            questionary.Choice("Cancel", value="cancel"),
        ],
    )
    if action != "logout":
        console.print("[dim]The current Codex session was kept.[/dim]")
        return True
    return logout_codex(console)
