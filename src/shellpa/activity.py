"""Unified ShellPa activity, approval, and first-run interaction surfaces."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from rich.console import Console
from rich.status import Status

from .icons import ui_icon, unicode_icons_supported
from .ux import UXSettings, active_theme, save_ux_settings


class ActivityState(str, Enum):
    GENERATING = "generating"
    REVIEWING = "reviewing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    RECOVERING = "recovering"


ACTIVITY_LABELS = {
    ActivityState.GENERATING: "Understanding your request…",
    ActivityState.REVIEWING: "Reviewing command safety…",
    ActivityState.AWAITING_APPROVAL: "Waiting for your decision",
    ActivityState.EXECUTING: "Executing command…",
    ActivityState.RECOVERING: "Preparing a correction…",
}


@contextmanager
def activity_status(
    console: Console,
    state: ActivityState,
    settings: UXSettings,
) -> Iterator[None]:
    """Show motion only while real work represented by the state is happening."""
    theme = active_theme(settings)
    label = ACTIVITY_LABELS[state]
    text = f"[bold {theme.accent}]{ui_icon('assistant')} ShellPa · {label}[/]"
    if (
        console.is_terminal
        and settings.animation == "full"
        and not settings.reduced_motion
    ):
        with console.status(text, spinner="dots"):
            yield
        return
    console.print(text)
    yield


class ExecutionActivity:
    """Animate silent execution, then yield the terminal to real process output."""

    def __init__(self, console: Console, settings: UXSettings):
        self.console = console
        self.settings = settings
        self._status: Status | None = None
        self._started = False
        self._yielded_to_output = False

    def start(self, command: str) -> None:
        if self._started:
            return
        self._started = True
        theme = active_theme(self.settings)
        label = (
            f"[bold {theme.accent}]{ui_icon('assistant')} ShellPa · "
            "Executing command…[/]"
        )
        if (
            self.console.is_terminal
            and self.settings.animation == "full"
            and not self.settings.reduced_motion
        ):
            self._status = self.console.status(label, spinner="dots")
            self._status.start()
        else:
            self.console.print(label)

    def before_output(self) -> None:
        if self._yielded_to_output:
            return
        self._yielded_to_output = True
        if self._status is not None:
            self._status.stop()
            self._status = None

    def finish(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None


APPROVAL_FRAMES = ("?", "¿", "?", "·")
ASCII_APPROVAL_FRAMES = ("?", ".", "?", ".")


def _approval_content(
    selected: list[int],
    settings: UXSettings,
) -> FormattedText:
    theme = active_theme(settings)
    frames = APPROVAL_FRAMES if unicode_icons_supported() else ASCII_APPROVAL_FRAMES
    frame = (
        frames[int(time.monotonic() * 3) % len(frames)]
        if settings.animation == "full" and not settings.reduced_motion
        else "?"
    )
    choices = ("Yes, execute", "No, cancel")
    content: list[tuple[str, str]] = [
        (f"fg:{theme.identity} bold", f"{frame} ShellPa"),
        (f"fg:{theme.accent}", " · Execute this command?\n\n"),
    ]
    for index, choice in enumerate(choices):
        marker = (
            ("❯" if unicode_icons_supported() else ">") if index == selected[0] else " "
        )
        style = (
            f"fg:{theme.identity} bold reverse"
            if index == selected[0]
            else f"fg:{theme.muted}"
        )
        content.append((style, f"  {marker} {choice}\n"))
    content.append(
        (f"fg:{theme.muted}", "\nUp/Down choose  ·  Enter confirm  ·  Esc cancel")
    )
    return FormattedText(content)


def select_standard_approval(
    settings: UXSettings,
    *,
    input_stream=None,
    output_stream=None,
) -> bool:
    """Collect a safe-default approval through a ShellPa-native selector."""
    selected = [1]  # No is the safe Enter-key default.
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: _approval_content(selected, settings),
        focusable=True,
    )

    @bindings.add("up")
    @bindings.add("down")
    def _toggle(event) -> None:
        selected[0] = 1 - selected[0]
        event.app.invalidate()

    @bindings.add("y")
    def _yes(event) -> None:
        event.app.exit(result=True)

    @bindings.add("n")
    @bindings.add("escape")
    @bindings.add("c-c")
    def _no(event) -> None:
        event.app.exit(result=False)

    @bindings.add("enter")
    def _confirm(event) -> None:
        event.app.exit(result=selected[0] == 0)

    application: Application[bool] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        refresh_interval=(
            0.3
            if settings.animation == "full" and not settings.reduced_motion
            else None
        ),
        input=input_stream,
        output=output_stream,
    )
    return application.run()


ONBOARDING_PAGES = (
    (
        "Start with the outcome",
        "Tell ShellPa what you want to accomplish in ordinary language.",
    ),
    (
        "See the command before it runs",
        "Review the native command, its scope, and the local safety assessment.",
    ),
    (
        "You remain in control",
        "ShellPa applies the required permission level. You decide what runs.",
    ),
)


def _onboarding_content(page: list[int], settings: UXSettings) -> FormattedText:
    theme = active_theme(settings)
    title, body = ONBOARDING_PAGES[page[0]]
    progress = "  ".join(
        "●" if index == page[0] else "○" for index in range(len(ONBOARDING_PAGES))
    )
    if not unicode_icons_supported():
        progress = "  ".join(
            "[*]" if index == page[0] else "[ ]"
            for index in range(len(ONBOARDING_PAGES))
        )
    last_page = page[0] == len(ONBOARDING_PAGES) - 1
    return FormattedText(
        [
            (
                f"fg:{theme.identity} bold",
                f"{ui_icon('assistant')} Welcome to ShellPa\n\n",
            ),
            (f"fg:{theme.accent} bold", f"{title}\n"),
            ("", f"{body}\n\n"),
            (f"fg:{theme.identity}", f"{progress}\n\n"),
            (
                f"fg:{theme.muted}",
                "Enter start  ·  Left back  ·  Esc skip"
                if last_page
                else "Enter next  ·  Left back  ·  Esc skip",
            ),
        ]
    )


def run_first_time_onboarding(
    console: Console,
    settings: UXSettings,
    *,
    input_stream=None,
    output_stream=None,
    persist: bool = True,
) -> bool:
    """Show the introduction once. Return whether a UI was displayed."""
    if settings.onboarding_complete:
        return False
    if input_stream is None and not console.is_terminal:
        return False

    page = [0]
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: _onboarding_content(page, settings),
        focusable=True,
    )

    @bindings.add("enter")
    @bindings.add("right")
    def _next(event) -> None:
        if page[0] == len(ONBOARDING_PAGES) - 1:
            event.app.exit(result=True)
        else:
            page[0] += 1
            event.app.invalidate()

    @bindings.add("left")
    def _previous(event) -> None:
        page[0] = max(0, page[0] - 1)
        event.app.invalidate()

    @bindings.add("escape")
    @bindings.add("c-c")
    def _skip(event) -> None:
        event.app.exit(result=False)

    application: Application[bool] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        input=input_stream,
        output=output_stream,
    )
    application.run()
    settings.onboarding_complete = True
    if persist:
        try:
            save_ux_settings(settings)
        except OSError as exc:
            console.print(
                "[yellow]ShellPa could not remember the onboarding choice: "
                f"{exc}[/yellow]"
            )
    return True
