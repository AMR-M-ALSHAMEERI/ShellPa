"""Keyboard-friendly interactive ShellPa session and slash-command routing."""

from __future__ import annotations

import os
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application, get_app
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from rich.console import Console
from rich.table import Table

from .about import run_about_menu
from .diagnostics import display_doctor, run_doctor
from .icons import model_icon, shell_icon, ui_icon, unicode_icons_supported
from .models import PermissionMode, WorkspaceContext
from .setup import run_setup_wizard
from .ux import (
    THEMES,
    UXSettings,
    active_theme,
    prompt_style,
    save_ux_settings,
)
from .workspace import detect_workspace
from .workspace_ui import display_workspace_context, format_workspace_identity

SLASH_COMMANDS = (
    "/help",
    "/mode",
    "/model",
    "/config",
    "/theme",
    "/motion",
    "/animation",
    "/doctor",
    "/context",
    "/about",
    "/clear",
    "/history",
    "/exit",
)

THEME_ORDER = ("ocean", "aurora", "minimal", "contrast", "ansi")
IDLE_FRAMES = ("✦", "✧", "·", "✧")
ASCII_IDLE_FRAMES = ("*", "+", ".", "+")
MODE_ORDER = (
    PermissionMode.ASK,
    PermissionMode.PLAN,
    PermissionMode.TRUSTED,
)
MOTION_ORDER = ("full", "compact", "off")


@dataclass(frozen=True)
class ModePresentation:
    label: str
    description: str
    color_role: str
    frames: tuple[str, ...]
    ascii_frames: tuple[str, ...]


MODE_PRESENTATIONS = {
    PermissionMode.ASK: ModePresentation(
        "Ask",
        "Confirm before ShellPa executes state-changing commands.",
        "caution",
        ("?", "¿", "?", "·"),
        ("?", ".", "?", "."),
    ),
    PermissionMode.PLAN: ModePresentation(
        "Plan",
        "Generate, explain, and review commands without executing them.",
        "accent",
        ("◇", "◆", "◇", "·"),
        ("<", ">", "<", "."),
    ),
    PermissionMode.TRUSTED: ModePresentation(
        "Trusted",
        "Auto-run known read-only commands; all other safeguards remain active.",
        "success",
        ("✓", "◉", "✓", "·"),
        ("OK", "+", "OK", "."),
    ),
}


def mode_icon(mode: PermissionMode, *, animated: bool = False) -> str:
    presentation = MODE_PRESENTATIONS[mode]
    frames = (
        presentation.frames if unicode_icons_supported() else presentation.ascii_frames
    )
    if not animated:
        return frames[0]
    return frames[int(time.monotonic() * 3) % len(frames)]


@dataclass
class InteractiveState:
    mode: PermissionMode
    model_name: str | None
    env_info: dict
    settings: UXSettings
    workspace: WorkspaceContext | None = None
    requests: list[str] = field(default_factory=list)
    should_exit: bool = False


class StatusFooter:
    def __init__(self, state: InteractiveState):
        self.state = state

    def __call__(self) -> HTML:
        width = shutil.get_terminal_size((100, 24)).columns
        parts = [f"{mode_icon(self.state.mode)} {self.state.mode.value.upper()}"]
        if width >= 72:
            parts.append(
                f"{model_icon(self.state.model_name)} "
                f"{self.state.model_name or 'no model'}"
            )
        shell = self.state.env_info.get("shell", "unknown")
        parts.append(f"{shell_icon(shell)} {shell}")
        if self.state.workspace is not None and width >= 60:
            parts.append(format_workspace_identity(self.state.workspace))
        current_directory = Path.cwd()
        parts.append(str(current_directory) if width >= 100 else current_directory.name)
        return HTML(f"  {escape('  |  '.join(parts))}  ")


def _key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _insert_newline(event) -> None:
        event.current_buffer.insert_text("\n")

    return bindings


def _show_help(console: Console) -> None:
    table = Table(title="ShellPa controls", show_header=False)
    table.add_column(style="bold cyan")
    table.add_column()
    rows = (
        ("/help", "Show these controls"),
        ("/mode [ask|plan|trusted]", "View or change permission mode"),
        ("/model [name]", "View or change the model for this session"),
        ("/config", "Run the provider configuration wizard"),
        ("/theme [ocean|aurora|minimal|contrast|ansi]", "Preview or change theme"),
        ("/motion [full|compact|off]", "Change startup animation"),
        ("/doctor", "Run local configuration and environment checks"),
        ("/context", "Inspect workspace facts and provider-safe context"),
        ("/about", "Show ShellPa identity and version"),
        ("/clear or Ctrl+L", "Clear visible output"),
        ("/history", "Show requests from this session"),
        ("/exit", "End the session"),
        ("Alt+Enter", "Insert a newline"),
        ("Ctrl+C", "Cancel the current input or work"),
    )
    for row in rows:
        table.add_row(*row)
    console.print(table)


def _idle_prompt(settings: UXSettings) -> Callable[[], FormattedText]:
    def render() -> FormattedText:
        theme = active_theme(settings)
        try:
            has_text = bool(get_app().current_buffer.text)
        except Exception:
            has_text = False
        animated = (
            settings.animation == "full"
            and not settings.reduced_motion
            and not has_text
        )
        frames = IDLE_FRAMES if unicode_icons_supported() else ASCII_IDLE_FRAMES
        frame = (
            frames[int(time.monotonic() * 4) % len(frames)]
            if animated
            else ui_icon("assistant")
        )
        return FormattedText(
            [
                (f"fg:{theme.identity} bold", f"{frame} ShellPa"),
                (f"fg:{theme.accent} bold", " › "),
            ]
        )

    return render


def _theme_selector_content(selected_index: list[int]) -> FormattedText:
    selected_name = THEME_ORDER[selected_index[0]]
    selected_theme = THEMES[selected_name]
    content: list[tuple[str, str]] = [
        (f"fg:{selected_theme.identity} bold", "Select a ShellPa theme\n\n")
    ]
    for index, name in enumerate(THEME_ORDER):
        theme = THEMES[name]
        marker = (
            ("❯" if unicode_icons_supported() else ">")
            if index == selected_index[0]
            else " "
        )
        style = (
            f"fg:{selected_theme.identity} bold reverse"
            if index == selected_index[0]
            else f"fg:{selected_theme.muted}"
        )
        content.append((style, f" {marker} {ui_icon('theme')} {theme.label}\n"))
    content.extend(
        [
            ("", "\n"),
            (f"fg:{selected_theme.identity} bold", "Live preview\n"),
            (
                f"fg:{selected_theme.accent}",
                f"{ui_icon('assistant')} ShellPa › explain this project\n",
            ),
            (
                f"fg:{selected_theme.success}",
                f"{ui_icon('success')} Completed successfully\n",
            ),
            (
                f"fg:{selected_theme.caution}",
                f"{ui_icon('caution')} Confirmation required\n",
            ),
            (
                f"fg:{selected_theme.danger}",
                f"{ui_icon('failure')} High-risk operation\n",
            ),
            (
                f"fg:{selected_theme.muted}",
                "\nUp/Down preview  ·  Enter apply  ·  Esc cancel",
            ),
        ]
    )
    return FormattedText(content)


def select_theme_interactively(
    current_theme: str,
    *,
    input_stream=None,
    output_stream=None,
) -> str | None:
    """Open a small live-preview selector without changing the main REPL layout."""
    selected_index = [
        THEME_ORDER.index(current_theme) if current_theme in THEME_ORDER else 0
    ]
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: _theme_selector_content(selected_index),
        focusable=True,
    )

    @bindings.add("up")
    def _previous(event) -> None:
        selected_index[0] = (selected_index[0] - 1) % len(THEME_ORDER)
        event.app.invalidate()

    @bindings.add("down")
    def _next(event) -> None:
        selected_index[0] = (selected_index[0] + 1) % len(THEME_ORDER)
        event.app.invalidate()

    @bindings.add("enter")
    def _apply(event) -> None:
        event.app.exit(result=THEME_ORDER[selected_index[0]])

    @bindings.add("escape")
    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=None)

    application: Application[str | None] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        input=input_stream,
        output=output_stream,
    )
    return application.run()


def _mode_selector_content(
    selected_index: list[int],
    state: InteractiveState,
) -> FormattedText:
    theme = active_theme(state.settings)
    selected_mode = MODE_ORDER[selected_index[0]]
    selected = MODE_PRESENTATIONS[selected_mode]
    selected_color = getattr(theme, selected.color_role)
    content: list[tuple[str, str]] = [
        (f"fg:{selected_color} bold", "Select permission mode\n\n")
    ]
    for index, mode in enumerate(MODE_ORDER):
        presentation = MODE_PRESENTATIONS[mode]
        marker = (
            ("❯" if unicode_icons_supported() else ">")
            if index == selected_index[0]
            else " "
        )
        color = getattr(theme, presentation.color_role)
        style = (
            f"fg:{selected_color} bold reverse"
            if index == selected_index[0]
            else f"fg:{color}"
        )
        content.append((style, f"  {marker} {mode_icon(mode)} {presentation.label}\n"))
    selected_icon = mode_icon(
        selected_mode,
        animated=(
            state.settings.animation == "full" and not state.settings.reduced_motion
        ),
    )
    content.extend(
        [
            ("", "\n"),
            (
                f"fg:{selected_color} bold",
                f"{selected_icon} {selected.label} mode\n",
            ),
            ("", f"{selected.description}\n"),
            (
                f"fg:{theme.muted}",
                "\nUp/Down preview  ·  Enter apply  ·  Esc cancel",
            ),
        ]
    )
    return FormattedText(content)


def select_mode_interactively(
    state: InteractiveState,
    *,
    input_stream=None,
    output_stream=None,
) -> PermissionMode | None:
    selected_index = [MODE_ORDER.index(state.mode)]
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: _mode_selector_content(selected_index, state),
        focusable=True,
    )

    @bindings.add("up")
    def _previous(event) -> None:
        selected_index[0] = (selected_index[0] - 1) % len(MODE_ORDER)
        event.app.invalidate()

    @bindings.add("down")
    def _next(event) -> None:
        selected_index[0] = (selected_index[0] + 1) % len(MODE_ORDER)
        event.app.invalidate()

    @bindings.add("enter")
    def _apply(event) -> None:
        event.app.exit(result=MODE_ORDER[selected_index[0]])

    @bindings.add("escape")
    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=None)

    application: Application[PermissionMode | None] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        refresh_interval=(
            0.3
            if state.settings.animation == "full" and not state.settings.reduced_motion
            else None
        ),
        input=input_stream,
        output=output_stream,
    )
    return application.run()


def _select_mode(state: InteractiveState) -> PermissionMode | None:
    return select_mode_interactively(state)


def _motion_selector_content(
    selected_index: list[int],
    state: InteractiveState,
) -> FormattedText:
    theme = active_theme(state.settings)
    selected = MOTION_ORDER[selected_index[0]]
    labels = {
        "full": "Full",
        "compact": "Compact",
        "off": "Off",
    }
    descriptions = {
        "full": "Short motion for startup, waiting, activity, and selection.",
        "compact": "Static ShellPa identity with no continuous movement.",
        "off": "No decorative startup presentation or animated state.",
    }
    full_frames = IDLE_FRAMES if unicode_icons_supported() else ASCII_IDLE_FRAMES
    previews = {
        "full": full_frames[int(time.monotonic() * 4) % len(full_frames)],
        "compact": ui_icon("assistant"),
        "off": "-",
    }
    content: list[tuple[str, str]] = [
        (f"fg:{theme.identity} bold", "Select motion\n\n")
    ]
    for index, name in enumerate(MOTION_ORDER):
        marker = (
            ("❯" if unicode_icons_supported() else ">")
            if index == selected_index[0]
            else " "
        )
        style = (
            f"fg:{theme.identity} bold reverse"
            if index == selected_index[0]
            else f"fg:{theme.muted}"
        )
        content.append((style, f"  {marker} {previews[name]} {labels[name]}\n"))
    content.extend(
        [
            ("", "\n"),
            (
                f"fg:{theme.accent} bold",
                f"{previews[selected]} ShellPa · {labels[selected]} preview\n",
            ),
            ("", f"{descriptions[selected]}\n"),
            (
                f"fg:{theme.muted}",
                "\nUp/Down preview  ·  Enter apply  ·  Esc cancel",
            ),
        ]
    )
    return FormattedText(content)


def select_motion_interactively(
    state: InteractiveState,
    *,
    input_stream=None,
    output_stream=None,
) -> str | None:
    current = (
        state.settings.animation if state.settings.animation in MOTION_ORDER else "full"
    )
    selected_index = [MOTION_ORDER.index(current)]
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: _motion_selector_content(selected_index, state),
        focusable=True,
    )

    @bindings.add("up")
    def _previous(event) -> None:
        selected_index[0] = (selected_index[0] - 1) % len(MOTION_ORDER)
        event.app.invalidate()

    @bindings.add("down")
    def _next(event) -> None:
        selected_index[0] = (selected_index[0] + 1) % len(MOTION_ORDER)
        event.app.invalidate()

    @bindings.add("enter")
    def _apply(event) -> None:
        event.app.exit(result=MOTION_ORDER[selected_index[0]])

    @bindings.add("escape")
    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=None)

    application: Application[str | None] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        refresh_interval=0.25,
        input=input_stream,
        output=output_stream,
    )
    return application.run()


def _select_motion(state: InteractiveState) -> str | None:
    return select_motion_interactively(state)


def _show_doctor(console: Console, state: InteractiveState) -> None:
    display_doctor(console, run_doctor())


def handle_slash_command(
    line: str,
    state: InteractiveState,
    console: Console,
) -> bool:
    """Handle a slash command. Return True when the input was a slash command."""
    if not line.startswith("/"):
        return False
    command, _, argument = line.strip().partition(" ")
    argument = argument.strip()

    if command == "/help":
        _show_help(console)
    elif command == "/mode":
        if not argument:
            if _has_interactive_terminal():
                selected_mode = _select_mode(state)
                if selected_mode is not None:
                    state.mode = selected_mode
                    console.print(
                        f"Permission mode changed to [bold]{state.mode.value}[/bold]."
                    )
            else:
                console.print(f"Current mode: [bold]{state.mode.value}[/bold]")
        else:
            try:
                state.mode = PermissionMode(argument.lower())
                console.print(
                    f"Permission mode changed to [bold]{state.mode.value}[/bold]."
                )
            except ValueError:
                console.print(
                    "[yellow]Use: /mode ask, /mode plan, or /mode trusted[/yellow]"
                )
    elif command == "/model":
        if not argument:
            console.print(
                f"Current model: [bold]{state.model_name or 'not configured'}[/bold]"
            )
        else:
            state.model_name = argument
            os.environ["SHELLPA_MODEL"] = argument
            console.print(
                f"Session model changed to [bold]{argument}[/bold]. "
                "[dim]Run /config to save provider settings permanently.[/dim]"
            )
    elif command == "/config":
        if run_setup_wizard():
            state.model_name = os.environ.get("SHELLPA_MODEL")
    elif command == "/theme":
        if not argument:
            if _has_interactive_terminal():
                selected_theme = select_theme_interactively(state.settings.theme)
                if selected_theme is not None:
                    state.settings.theme = selected_theme
                    save_ux_settings(state.settings)
                    console.print(
                        f"Theme changed to [bold]{THEMES[selected_theme].label}[/bold]."
                    )
            else:
                console.print(
                    "Themes: "
                    + ", ".join(
                        f"[bold]{name}[/bold] ({THEMES[name].label})"
                        for name in THEME_ORDER
                    )
                )
        elif argument.lower() in THEMES:
            state.settings.theme = argument.lower()
            save_ux_settings(state.settings)
            console.print(
                f"Theme changed to [bold]{THEMES[argument.lower()].label}[/bold]."
            )
        else:
            console.print(
                "[yellow]Use: /theme ocean, aurora, minimal, contrast, or ansi[/yellow]"
            )
    elif command in {"/motion", "/animation"}:
        if not argument:
            if _has_interactive_terminal():
                selected_motion = _select_motion(state)
                if selected_motion is not None:
                    state.settings.animation = selected_motion
                    state.settings.reduced_motion = selected_motion != "full"
                    save_ux_settings(state.settings)
                    console.print(
                        f"Startup animation changed to [bold]{selected_motion}[/bold]."
                    )
            else:
                console.print(
                    f"Startup animation: [bold]{state.settings.animation}[/bold]"
                )
        elif argument.lower() in {"full", "compact", "off"}:
            state.settings.animation = argument.lower()
            state.settings.reduced_motion = argument.lower() != "full"
            save_ux_settings(state.settings)
            console.print(
                f"Startup animation changed to [bold]{argument.lower()}[/bold]."
            )
        else:
            console.print("[yellow]Use: /motion full, compact, or off[/yellow]")
    elif command == "/doctor":
        _show_doctor(console, state)
    elif command == "/context":
        state.workspace = detect_workspace()
        display_workspace_context(console, state.workspace)
    elif command == "/about":
        run_about_menu(
            console,
            state.settings,
            return_label="Return to ShellPa",
        )
    elif command == "/clear":
        console.clear()
    elif command == "/history":
        if not state.requests:
            console.print("[dim]No requests in this session.[/dim]")
        else:
            for index, request in enumerate(state.requests, 1):
                console.print(f"[bold]{index:>3}[/bold]  {request}")
    elif command == "/exit":
        state.should_exit = True
    else:
        console.print(f"[yellow]Unknown command: {command}. Try /help.[/yellow]")
    return True


def _has_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _run_redirected_session(
    console: Console,
    state: InteractiveState,
    process: Callable[[str, PermissionMode], None],
) -> None:
    """Keep redirected input useful without initializing a terminal UI."""
    for raw_line in sys.stdin:
        user_input = raw_line.strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            state.should_exit = True
            break
        if handle_slash_command(user_input, state, console):
            if state.should_exit:
                break
            continue
        state.requests.append(user_input)
        process(user_input, state.mode)


def run_interactive_session(
    console: Console,
    state: InteractiveState,
    process: Callable[[str, PermissionMode], None],
) -> None:
    if not _has_interactive_terminal():
        _run_redirected_session(console, state, process)
        return

    completer = WordCompleter(SLASH_COMMANDS, sentence=True, ignore_case=True)
    session: PromptSession[str] = PromptSession(
        history=InMemoryHistory(),
        completer=completer,
        complete_while_typing=True,
        key_bindings=_key_bindings(),
    )
    footer = StatusFooter(state)
    console.print("[dim]Type /help for controls. Alt+Enter inserts a new line.[/dim]\n")

    while not state.should_exit:
        try:
            user_input = session.prompt(
                _idle_prompt(state.settings),
                bottom_toolbar=footer,
                style=prompt_style(state.settings),
                prompt_continuation=HTML(
                    "<continuation>      "
                    + ("·" if unicode_icons_supported() else ".")
                    + " </continuation>"
                ),
                refresh_interval=(
                    0.25
                    if state.settings.animation == "full"
                    and not state.settings.reduced_motion
                    else None
                ),
            ).strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                state.should_exit = True
                continue
            if handle_slash_command(user_input, state, console):
                continue
            state.requests.append(user_input)
            process(user_input, state.mode)
            console.print()
        except KeyboardInterrupt:
            console.print("[yellow]Input cancelled.[/yellow]")
        except EOFError:
            break
    console.print("[bold cyan]Goodbye![/bold cyan]")
