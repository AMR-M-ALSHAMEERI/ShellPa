"""Interactive visual language, themes, and privacy-safe UX settings."""

from __future__ import annotations

import json
import os
import select
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import questionary
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from . import __version__
from .icons import model_icon, shell_icon, unicode_icons_supported
from .identity import MICRO_MARK, LogoTone, reveal_logo, terminal_logo
from .models import CommandProposal, ExecutionResult, RiskAssessment, RiskLevel


@dataclass(frozen=True)
class ThemeSpec:
    name: str
    label: str
    identity: str
    accent: str
    success: str
    caution: str
    danger: str
    muted: str


THEMES: dict[str, ThemeSpec] = {
    "ocean": ThemeSpec(
        "ocean",
        "Ocean / Aurora",
        "#00eeff",
        "#0088ff",
        "#39d98a",
        "#ffd166",
        "#ff5c77",
        "#7895b2",
    ),
    "shellpa": ThemeSpec(
        "shellpa",
        "ShellPa Signature",
        "#5b8fd8",
        "#d2ad58",
        "#71b7a0",
        "#d2ad58",
        "#d06f79",
        "#8795aa",
    ),
    "minimal": ThemeSpec(
        "minimal",
        "Minimal Dark",
        "#d7d7d7",
        "#87afd7",
        "#87d787",
        "#d7af87",
        "#d78787",
        "#808080",
    ),
    "aurora": ThemeSpec(
        "aurora",
        "Aurora Violet",
        "#c084fc",
        "#22d3ee",
        "#4ade80",
        "#fbbf24",
        "#fb7185",
        "#94a3b8",
    ),
    "contrast": ThemeSpec(
        "contrast",
        "High Contrast",
        "#ffffff",
        "#00ffff",
        "#00ff00",
        "#ffff00",
        "#ff0000",
        "#c0c0c0",
    ),
    "ansi": ThemeSpec(
        "ansi",
        "ANSI / No Color",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
    ),
}


@dataclass
class UXSettings:
    theme: str = "shellpa"
    animation: str = "full"
    reduced_motion: bool = False
    onboarding_complete: bool = False
    update_notifications: str = "manual"

    def normalized(self) -> UXSettings:
        requested_theme = "shellpa" if self.theme == "midnight" else self.theme
        theme = requested_theme if requested_theme in THEMES else "shellpa"
        animation = (
            self.animation if self.animation in {"full", "compact", "off"} else "full"
        )
        update_notifications = (
            self.update_notifications
            if self.update_notifications in {"weekly", "manual", "off"}
            else "manual"
        )
        return UXSettings(
            theme,
            animation,
            bool(self.reduced_motion),
            bool(self.onboarding_complete),
            update_notifications,
        )


def get_settings_path() -> Path:
    return Path.home() / ".shellpa" / "settings.json"


def load_ux_settings(path: Path | None = None) -> UXSettings:
    settings_path = path or get_settings_path()
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return UXSettings()
        return UXSettings(
            theme=str(payload.get("theme", "shellpa")),
            animation=str(payload.get("animation", "full")),
            reduced_motion=bool(payload.get("reduced_motion", False)),
            onboarding_complete=bool(payload.get("onboarding_complete", False)),
            update_notifications=str(payload.get("update_notifications", "manual")),
        ).normalized()
    except (OSError, ValueError, TypeError):
        return UXSettings()


def save_ux_settings(settings: UXSettings, path: Path | None = None) -> Path:
    settings_path = path or get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = settings_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(asdict(settings.normalized()), indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(settings_path)
    return settings_path


def active_theme(settings: UXSettings) -> ThemeSpec:
    if os.environ.get("NO_COLOR") is not None:
        return THEMES["ansi"]
    return THEMES[settings.normalized().theme]


def prompt_style(settings: UXSettings) -> Style:
    theme = active_theme(settings)
    return Style.from_dict(
        {
            "prompt": f"bold {theme.identity}",
            "continuation": theme.muted,
            "bottom-toolbar": f"bg:#001b2e {theme.identity}"
            if theme.name == "ocean"
            else f"reverse {theme.identity}",
            "completion-menu.completion": f"bg:#202020 {theme.identity}",
            "completion-menu.completion.current": f"bg:{theme.accent} #ffffff bold"
            if theme.name != "ansi"
            else "reverse bold",
        }
    )


def questionary_style(settings: UXSettings) -> questionary.Style:
    theme = active_theme(settings)
    return questionary.Style(
        [
            ("qmark", f"fg:{theme.identity} bold"),
            ("question", "fg:#ffffff bold"),
            ("answer", f"fg:{theme.identity} bold"),
            ("pointer", f"fg:{theme.identity} bold"),
            ("highlighted", f"fg:{theme.accent} bold"),
            ("selected", f"fg:{theme.identity}"),
            ("instruction", f"fg:{theme.muted}"),
            ("text", "fg:#ffffff"),
        ]
    )


@contextmanager
def _keypress_mode():
    """Temporarily enable single-key reads on POSIX, restoring terminal state."""
    if os.name == "nt" or not sys.stdin.isatty():
        yield
        return
    try:
        import termios
        import tty
    except ImportError:
        yield
        return
    try:
        descriptor = sys.stdin.fileno()
        terminal_attributes = getattr(termios, "tcgetattr")  # noqa: B009
        previous = terminal_attributes(descriptor)
        getattr(tty, "setcbreak")(descriptor)  # noqa: B009
    except OSError:
        yield
        return
    try:
        yield
    finally:
        getattr(termios, "tcsetattr")(  # noqa: B009
            descriptor,
            getattr(termios, "TCSADRAIN"),  # noqa: B009
            previous,
        )


def _skip_requested() -> bool:
    if not sys.stdin.isatty():
        return False
    if os.name == "nt":
        try:
            import msvcrt

            key_available = getattr(msvcrt, "kbhit")  # noqa: B009
            read_key = getattr(msvcrt, "getwch")  # noqa: B009
            if key_available():
                read_key()
                return True
        except (ImportError, OSError):
            return False
        return False
    try:
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if readable:
            sys.stdin.read(1)
            return True
    except (OSError, ValueError):
        return False
    return False


def render_brand_header(
    console: Console,
    settings: UXSettings,
    env_info: dict,
    model_name: str | None,
    *,
    color: str | None = None,
) -> None:
    theme = active_theme(settings)
    identity = color or theme.identity
    console.print(
        brand_logo_text(
            settings,
            width=console.width,
            identity_override=identity,
        )
    )
    console.print()
    console.print(
        Text.assemble(
            ("  Natural language. Native commands. Your authority.\n\n", theme.muted),
            ("  ", theme.muted),
            (
                f"{shell_icon(env_info.get('shell'))} "
                f"{env_info.get('shell', 'unknown')}",
                f"bold {theme.accent}",
            ),
            ("  ·  ", theme.muted),
            (
                f"{model_icon(model_name)} {model_name or 'model not configured'}",
                theme.muted,
            ),
        )
    )
    console.print()


def brand_logo_text(
    settings: UXSettings,
    *,
    width: int,
    identity_override: str | None = None,
    reveal_progress: float = 1.0,
) -> Text:
    """Build the shared terminal-native logo used by every launch surface."""
    theme = active_theme(settings)
    identity = identity_override or theme.identity
    frame = reveal_logo(
        terminal_logo(
            width,
            unicode=(
                theme.name != "ansi"
                and os.environ.get("SHELLPA_ICONS") != "ascii"
                and unicode_icons_supported()
            ),
        ),
        reveal_progress,
    )
    rendered = Text()
    tone_styles = {
        LogoTone.PRIMARY: f"bold {identity}",
        LogoTone.SECONDARY: f"bold {theme.muted}",
        LogoTone.ACCENT: f"bold {theme.accent}",
        LogoTone.WORDMARK: f"bold {theme.accent}",
    }
    for index, line in enumerate(frame.styled_lines):
        for span in line:
            rendered.append(span.text, style=tone_styles[span.tone])
        if index == len(frame.lines) - 1 and reveal_progress >= 1.0:
            rendered.append(f"  v{__version__}", style=theme.muted)
        if index != len(frame.lines) - 1:
            rendered.append("\n")
    return rendered


def display_about(
    console: Console,
    settings: UXSettings,
) -> None:
    theme = active_theme(settings)
    details = Text()
    details.append(
        f"{MICRO_MARK} ShellPa v{__version__}\n",
        style=f"bold {theme.identity}",
    )
    details.append(
        "Natural language. Native commands. Your authority.\n\n",
        style=theme.accent,
    )
    details.append(
        "ShellPa translates user intent into a native command, reviews it "
        "locally, requests the required permission, and streams the real result.\n\n"
    )
    details.append("Developed by ", style=theme.muted)
    details.append("AMR", style=f"bold {theme.identity}")
    details.append(" & ", style=theme.muted)
    details.append("KHADIGA", style=f"bold {theme.accent}")
    console.print(
        Panel(
            details,
            title="About ShellPa",
            border_style=theme.identity,
            expand=False,
        )
    )


SESSION_STATEMENTS = (
    "What are we working on today?",
    "What would you like to get done?",
    "Tell me the outcome you want.",
    "Ready when you are.",
    "What are we building today?",
)


def session_greeting_copy(
    now: datetime | None = None,
    *,
    statement_index: int | None = None,
) -> tuple[str, str]:
    moment = now or datetime.now()
    if moment.hour < 12:
        greeting = "Good morning."
    elif moment.hour < 17:
        greeting = "Good afternoon."
    else:
        greeting = "Good evening."
    index = (
        statement_index
        if statement_index is not None
        else (moment.toordinal() + moment.hour) % len(SESSION_STATEMENTS)
    )
    return greeting, SESSION_STATEMENTS[index % len(SESSION_STATEMENTS)]


def display_session_greeting(
    console: Console,
    settings: UXSettings,
    *,
    now: datetime | None = None,
    statement_index: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Show curated ShellPa copy on every real interactive launch."""
    if not console.is_terminal:
        return
    normalized = settings.normalized()
    theme = active_theme(normalized)
    greeting, statement = session_greeting_copy(
        now,
        statement_index=statement_index,
    )
    final = Text.assemble(
        (f"{MICRO_MARK} {greeting}\n", f"bold {theme.identity}"),
        (f"  {statement}", theme.accent),
    )
    if normalized.animation != "full" or normalized.reduced_motion:
        console.print(final)
        console.print()
        return

    from rich.live import Live

    colors = (theme.muted, theme.accent, theme.identity)
    with _keypress_mode():
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            for color in colors:
                live.update(
                    Text.assemble(
                        (f"{MICRO_MARK} {greeting}\n", f"bold {color}"),
                        (f"  {statement}", color),
                    )
                )
                if _skip_requested():
                    break
                sleep(0.07)
    console.print(final)
    console.print()


def play_startup_reveal(
    console: Console,
    settings: UXSettings,
    env_info: dict,
    model_name: str | None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Render a short, skippable brand reveal only in interactive terminals."""
    normalized = settings.normalized()
    if normalized.animation == "off":
        return
    if (
        normalized.animation == "compact"
        or normalized.reduced_motion
        or not console.is_terminal
    ):
        render_brand_header(console, normalized, env_info, model_name)
        return

    from rich.live import Live

    duration = 1.0 if not normalized.onboarding_complete else 0.65
    frame_count = 20 if not normalized.onboarding_complete else 13
    with _keypress_mode():
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            for frame_index in range(frame_count + 1):
                progress = frame_index / frame_count
                eased = 1.0 - ((1.0 - progress) ** 2)
                live.update(
                    brand_logo_text(
                        normalized,
                        width=console.width,
                        reveal_progress=eased,
                    )
                )
                if _skip_requested():
                    break
                sleep(duration / frame_count)
    render_brand_header(console, normalized, env_info, model_name)


def risk_style(assessment: RiskAssessment, theme: ThemeSpec) -> str:
    return {
        RiskLevel.READ_ONLY: theme.success,
        RiskLevel.NORMAL: theme.caution,
        RiskLevel.UNKNOWN: theme.caution,
        RiskLevel.HIGH: theme.danger,
        RiskLevel.CRITICAL: f"bold {theme.danger}",
    }[assessment.risk_level]


def display_proposal_review(
    console: Console,
    proposal: CommandProposal,
    assessment: RiskAssessment,
    shell: str,
    settings: UXSettings,
) -> None:
    """Present command, purpose, scope, and risk as one decision surface."""
    theme = active_theme(settings)
    color = risk_style(assessment, theme)
    lexer = "powershell" if shell in {"powershell", "pwsh", "cmd"} else "bash"
    command = Syntax(
        proposal.command,
        lexer,
        theme="monokai" if theme.name != "ansi" else "bw",
        line_numbers=False,
        word_wrap=True,
    )
    title = (
        f"Proposed command · {assessment.risk_level.value.replace('_', ' ').upper()}"
    )
    console.print(Panel(command, title=title, border_style=color))

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="bold")
    facts.add_column(overflow="fold")
    facts.add_row("Purpose", proposal.explanation)
    if assessment.affected_targets:
        facts.add_row("Scope", "\n".join(assessment.affected_targets))
    facts.add_row("Safety", "\n".join(assessment.reasons))
    flags = []
    if assessment.requires_network:
        flags.append("network")
    if assessment.requires_privilege:
        flags.append("elevated privileges")
    if flags:
        facts.add_row("Flags", ", ".join(flags))
    console.print(facts)
    console.print()


def display_execution_result(
    console: Console,
    result: ExecutionResult,
    settings: UXSettings,
) -> None:
    theme = active_theme(settings)
    if result.success:
        console.print(
            f"[bold {theme.success}]{MICRO_MARK} Completed[/bold {theme.success}] "
            f"[{theme.muted}]in {result.duration_seconds:.2f}s[/{theme.muted}]"
        )


def display_execution_failure(
    console: Console,
    result: ExecutionResult,
    message: str,
    settings: UXSettings,
) -> None:
    theme = active_theme(settings)
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold")
    details.add_column(overflow="fold")
    details.add_row("Cause", Text(message))
    if result.exit_code is not None:
        details.add_row("Exit code", str(result.exit_code))
    details.add_row("Duration", f"{result.duration_seconds:.2f}s")
    if result.timed_out:
        details.add_row("Status", "Timed out")
    elif result.cancelled:
        details.add_row("Status", "Cancelled")
    console.print(
        Panel(details, title=f"{MICRO_MARK} Failed", border_style=theme.danger)
    )


def display_recovery_heading(
    console: Console,
    attempt: int,
    maximum: int,
    settings: UXSettings,
) -> None:
    theme = active_theme(settings)
    console.print(
        f"\n[bold {theme.accent}]Recovery attempt {attempt}/{maximum}[/bold {theme.accent}]"
    )
