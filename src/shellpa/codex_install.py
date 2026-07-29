"""Explicit, interactive installation support for the optional Codex SDK."""

from __future__ import annotations

import importlib
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Protocol

from rich.console import Console

from .codex_provider import CODEX_SDK_REQUIREMENT, codex_sdk_installed


class CompletedProcessLike(Protocol):
    returncode: int


InstallRunner = Callable[..., CompletedProcessLike]


def codex_install_command() -> list[str]:
    """Build the safe argv used to install into ShellPa's active interpreter."""
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        CODEX_SDK_REQUIREMENT,
    ]


def format_command(argv: Sequence[str]) -> str:
    """Format an argv list for manual use on the current operating system."""
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def install_codex_sdk(
    console: Console,
    *,
    runner: InstallRunner = subprocess.run,
) -> bool:
    """Install and verify the pinned SDK after the user has explicitly opted in."""
    command = codex_install_command()
    try:
        with console.status(
            "[bold cyan]Installing the embedded Codex provider...[/bold cyan]",
            spinner="dots",
        ):
            completed = runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                shell=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        console.print(
            f"[red]Codex installation could not start: {type(exc).__name__}.[/red]"
        )
        console.print(
            f"[dim]You can run this manually: {format_command(command)}[/dim]"
        )
        return False

    if completed.returncode != 0:
        console.print(
            f"[red]Codex installation failed (exit code {completed.returncode}).[/red]"
        )
        console.print(
            f"[dim]You can run this manually: {format_command(command)}[/dim]"
        )
        return False

    importlib.invalidate_caches()
    if not codex_sdk_installed():
        console.print(
            "[red]The installer finished, but ShellPa could not import the Codex SDK.[/red]"
        )
        console.print(f"[dim]Try this manually: {format_command(command)}[/dim]")
        return False

    console.print("[green]The embedded Codex provider is ready.[/green]")
    return True
