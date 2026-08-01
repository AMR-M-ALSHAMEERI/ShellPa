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
from prompt_toolkit.application import get_app
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.table import Table

from .about import run_about_menu
from .codex_auth import login_codex_interactively, logout_codex_interactively
from .diagnostics import display_doctor, run_doctor
from .icons import model_icon, shell_icon, ui_icon, unicode_icons_supported
from .identity import (
    MICRO_MARK,
    input_caret_frame,
    prompt_breath_level,
    prompt_mark_frame,
    signal_sweep_active,
)
from .models import PermissionMode, WorkspaceContext
from .selector import (
    SelectionOption,
    SelectorAction,
    select_interactively,
    selector_content,
)
from .setup import SetupOutcome, run_setup_wizard
from .updater import display_guided_update
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
    "/login",
    "/logout",
    "/theme",
    "/motion",
    "/animation",
    "/doctor",
    "/context",
    "/about",
    "/update",
    "/clear",
    "/history",
    "/exit",
)

THEME_ORDER = ("shellpa", "ocean", "aurora", "minimal", "contrast", "ansi")
IDLE_FRAMES = ("✦", "✧", "·", "✧")
ASCII_IDLE_FRAMES = ("*", "+", ".", "+")
MODE_ORDER = (
    PermissionMode.ASK,
    PermissionMode.PLAN,
    PermissionMode.TRUSTED,
)
MOTION_ORDER = ("full", "compact", "off")
UPDATE_NOTIFICATION_ORDER = ("weekly", "manual", "off")


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
        ("/login [device-code]", "Connect Codex to a ChatGPT account"),
        ("/logout", "Review and clear the Codex-managed account session"),
        (
            "/theme [shellpa|ocean|aurora|minimal|contrast|ansi]",
            "Preview or change theme",
        ),
        ("/motion [full|compact|off]", "Change startup animation"),
        ("/doctor", "Run local configuration and environment checks"),
        ("/context", "Inspect workspace facts and provider-safe context"),
        ("/about", "Show ShellPa identity and version"),
        (
            "/update [settings|weekly|manual|off]",
            "Check PyPI or configure update notifications",
        ),
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
    started_at: list[float | None] = [None]

    def render() -> FormattedText:
        theme = active_theme(settings)
        try:
            has_text = bool(get_app().current_buffer.text)
        except Exception:
            has_text = False
        motion_enabled = (
            settings.animation == "full"
            and not settings.reduced_motion
            and not has_text
        )
        now = time.monotonic()
        start = started_at[0]
        if start is None:
            start = now
            started_at[0] = start
        elapsed = max(0.0, now - start)
        mark = prompt_mark_frame(
            elapsed,
            has_input=has_text,
            motion_enabled=motion_enabled,
            unicode=unicode_icons_supported(),
        )
        caret = input_caret_frame(
            elapsed,
            has_input=has_text,
            motion_enabled=motion_enabled,
            unicode=unicode_icons_supported(),
        )
        signal_active = signal_sweep_active(
            elapsed,
            motion_enabled=motion_enabled,
        )
        breath_level = prompt_breath_level(
            elapsed,
            has_input=has_text,
            motion_enabled=motion_enabled,
        )
        mark_color = (
            theme.accent
            if signal_active
            else _blend_hex_color(theme.identity, theme.accent, breath_level * 0.55)
        )
        return FormattedText(
            [
                (f"fg:{theme.identity} bold", mark[:1]),
                (f"fg:{mark_color} bold", mark[1:]),
                (f"fg:{theme.identity} bold", " ShellPa"),
                (
                    f"fg:{theme.identity if signal_active else theme.accent} bold",
                    f" {caret} ",
                ),
            ]
        )

    return render


def _blend_hex_color(start: str, end: str, amount: float) -> str:
    """Blend two theme colors without changing prompt layout or terminal state."""
    bounded = max(0.0, min(1.0, amount))
    start_channels = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    end_channels = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    blended = tuple(
        round(source + (target - source) * bounded)
        for source, target in zip(start_channels, end_channels, strict=True)
    )
    return "#" + "".join(f"{channel:02x}" for channel in blended)


def _theme_selector_content(
    selected_index: list[int],
    current_theme: str | None = None,
) -> FormattedText:
    selected_name = THEME_ORDER[selected_index[0]]
    persisted_theme = current_theme if current_theme in THEME_ORDER else selected_name
    settings = UXSettings(theme=persisted_theme)
    return selector_content(
        "Select a ShellPa theme",
        tuple(SelectionOption(name, THEMES[name].label) for name in THEME_ORDER),
        selected_index[0],
        persisted_theme,
        settings,
        preview=_theme_preview,
        allow_back=True,
    )


def _theme_preview(name: str, settings: UXSettings) -> FormattedText:
    theme = THEMES[name]
    return FormattedText(
        [
            (f"fg:{theme.identity} bold", "Live preview\n"),
            (f"fg:{theme.accent}", f"{MICRO_MARK} ShellPa › explain this project\n"),
            (f"fg:{theme.success}", f"{MICRO_MARK} Completed successfully\n"),
            (f"fg:{theme.caution}", f"{MICRO_MARK} Confirmation required\n"),
            (f"fg:{theme.danger}", f"{MICRO_MARK} High-risk operation\n"),
        ]
    )


def select_theme_interactively(
    current_theme: str,
    *,
    input_stream=None,
    output_stream=None,
) -> str | None:
    """Open a small live-preview selector without changing the main REPL layout."""
    selected = current_theme if current_theme in THEME_ORDER else THEME_ORDER[0]
    result = select_interactively(
        "Select a ShellPa theme",
        tuple(SelectionOption(name, THEMES[name].label) for name in THEME_ORDER),
        selected,
        UXSettings(theme=selected),
        persisted_value=selected,
        preview=_theme_preview,
        allow_back=True,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    return result.value if result.action is SelectorAction.SELECT else None


def _mode_selector_content(
    selected_index: list[int],
    state: InteractiveState,
) -> FormattedText:
    options = tuple(
        SelectionOption(
            mode,
            MODE_PRESENTATIONS[mode].label,
            MODE_PRESENTATIONS[mode].description,
        )
        for mode in MODE_ORDER
    )
    return selector_content(
        "Select permission mode",
        options,
        selected_index[0],
        state.mode,
        state.settings,
        persisted_value=state.mode,
        preview=_mode_preview,
    )


def _mode_preview(mode: PermissionMode, settings: UXSettings) -> FormattedText:
    theme = active_theme(settings)
    selected_mode = mode
    selected = MODE_PRESENTATIONS[selected_mode]
    selected_color = getattr(theme, selected.color_role)
    selected_icon = mode_icon(
        selected_mode,
        animated=(settings.animation == "full" and not settings.reduced_motion),
    )
    return FormattedText(
        [
            (
                f"fg:{selected_color} bold",
                f"{selected_icon} {selected.label} mode\n",
            ),
        ]
    )


def select_mode_interactively(
    state: InteractiveState,
    *,
    input_stream=None,
    output_stream=None,
) -> PermissionMode | None:
    result = select_interactively(
        "Select permission mode",
        tuple(
            SelectionOption(
                mode,
                MODE_PRESENTATIONS[mode].label,
                MODE_PRESENTATIONS[mode].description,
            )
            for mode in MODE_ORDER
        ),
        state.mode,
        state.settings,
        persisted_value=state.mode,
        preview=_mode_preview,
        refresh_interval=(
            0.3
            if state.settings.animation == "full" and not state.settings.reduced_motion
            else None
        ),
        input_stream=input_stream,
        output_stream=output_stream,
    )
    return result.value if result.action is SelectorAction.SELECT else None


def _select_mode(state: InteractiveState) -> PermissionMode | None:
    return select_mode_interactively(state)


def _motion_selector_content(
    selected_index: list[int],
    state: InteractiveState,
) -> FormattedText:
    return selector_content(
        "Select motion",
        tuple(
            SelectionOption(name, _motion_label(name), _motion_description(name))
            for name in MOTION_ORDER
        ),
        selected_index[0],
        state.settings.animation,
        state.settings,
        persisted_value=state.settings.animation,
        preview=_motion_preview,
    )


def _motion_label(name: str) -> str:
    labels = {
        "full": "Full",
        "compact": "Compact",
        "off": "Off",
    }
    return labels[name]


def _motion_description(name: str) -> str:
    descriptions = {
        "full": "Short motion for startup, waiting, activity, and selection.",
        "compact": "Static ShellPa identity with no continuous movement.",
        "off": "No decorative startup presentation or animated state.",
    }
    return descriptions[name]


def _motion_preview(selected: str, settings: UXSettings) -> FormattedText:
    theme = active_theme(settings)
    full_frames = IDLE_FRAMES if unicode_icons_supported() else ASCII_IDLE_FRAMES
    previews = {
        "full": full_frames[int(time.monotonic() * 4) % len(full_frames)],
        "compact": ui_icon("assistant"),
        "off": "-",
    }
    return FormattedText(
        [
            (
                f"fg:{theme.accent} bold",
                f"{previews[selected]} ShellPa · {_motion_label(selected)} preview\n",
            ),
        ]
    )


def select_motion_interactively(
    state: InteractiveState,
    *,
    input_stream=None,
    output_stream=None,
) -> str | None:
    current = (
        state.settings.animation if state.settings.animation in MOTION_ORDER else "full"
    )
    result = select_interactively(
        "Select motion",
        tuple(
            SelectionOption(name, _motion_label(name), _motion_description(name))
            for name in MOTION_ORDER
        ),
        current,
        state.settings,
        persisted_value=current,
        preview=_motion_preview,
        refresh_interval=0.25,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    return result.value if result.action is SelectorAction.SELECT else None


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
        outcome = run_setup_wizard()
        if outcome is SetupOutcome.SAVED:
            state.model_name = os.environ.get("SHELLPA_MODEL")
        elif outcome is SetupOutcome.CANCELLED:
            console.print("[dim]Returned to ShellPa without saving.[/dim]")
    elif command == "/login":
        if argument and argument.lower() != "device-code":
            console.print("[yellow]Use: /login or /login device-code[/yellow]")
        else:
            login_codex_interactively(
                console,
                device_code=argument.lower() == "device-code",
            )
    elif command == "/logout":
        logout_codex_interactively(console)
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
                "[yellow]Use: /theme shellpa, ocean, aurora, minimal, "
                "contrast, or ansi[/yellow]"
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
    elif command == "/update":
        preference = argument.lower()
        if not preference:
            display_guided_update(console)
        elif preference == "settings":
            if _has_interactive_terminal():
                result = select_interactively(
                    "Update notifications",
                    (
                        SelectionOption(
                            "weekly",
                            "Weekly",
                            "Contact only PyPI, at most once every seven days.",
                        ),
                        SelectionOption(
                            "manual",
                            "Manual only",
                            "Check only when you run /update or shellpa update.",
                        ),
                        SelectionOption(
                            "off",
                            "Disabled",
                            "Do not run automatic update checks.",
                        ),
                    ),
                    state.settings.update_notifications,
                    state.settings,
                    persisted_value=state.settings.update_notifications,
                )
                if result.action is SelectorAction.SELECT and result.value is not None:
                    state.settings.update_notifications = result.value
                    save_ux_settings(state.settings)
            else:
                console.print(
                    "Update notifications: "
                    f"[bold]{state.settings.update_notifications}[/bold]"
                )
        elif preference in UPDATE_NOTIFICATION_ORDER:
            state.settings.update_notifications = preference
            save_ux_settings(state.settings)
            console.print(f"Update notifications set to [bold]{preference}[/bold].")
        else:
            console.print(
                "[yellow]Use: /update, /update settings, /update weekly, "
                "/update manual, or /update off[/yellow]"
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
