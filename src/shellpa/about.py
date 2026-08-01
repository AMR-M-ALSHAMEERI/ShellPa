"""Shared About actions for external and interactive ShellPa sessions."""

from __future__ import annotations

import webbrowser
from enum import Enum

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from rich.console import Console

from .icons import ui_icon, unicode_icons_supported
from .ux import UXSettings, active_theme, display_about

AMR_GITHUB_URL = "https://github.com/AMR-M-ALSHAMEERI"
KHADIGA_GITHUB_URL = "https://github.com/doji0x0"
SHELLPA_REPOSITORY_URL = "https://github.com/AMR-M-ALSHAMEERI/ShellPa"


class AboutAction(str, Enum):
    AMR_PROFILE = "amr_profile"
    KHADIGA_PROFILE = "khadiga_profile"
    REPOSITORY = "repository"
    RETURN = "return"
    CANCEL = "cancel"


ABOUT_URLS = {
    AboutAction.AMR_PROFILE: AMR_GITHUB_URL,
    AboutAction.KHADIGA_PROFILE: KHADIGA_GITHUB_URL,
    AboutAction.REPOSITORY: SHELLPA_REPOSITORY_URL,
}

ABOUT_ORDER = (
    AboutAction.AMR_PROFILE,
    AboutAction.KHADIGA_PROFILE,
    AboutAction.REPOSITORY,
    AboutAction.RETURN,
)


def _about_selector_content(
    selected_index: list[int],
    settings: UXSettings,
    return_label: str,
) -> FormattedText:
    theme = active_theme(settings)
    labels = {
        AboutAction.AMR_PROFILE: "AMR — GitHub profile",
        AboutAction.KHADIGA_PROFILE: "KHADIGA — GitHub profile",
        AboutAction.REPOSITORY: "ShellPa — GitHub repository",
        AboutAction.RETURN: return_label,
    }
    icons = {
        AboutAction.AMR_PROFILE: "◆",
        AboutAction.KHADIGA_PROFILE: "◆",
        AboutAction.REPOSITORY: "◇",
        AboutAction.RETURN: "←",
    }
    if not unicode_icons_supported():
        icons = {
            AboutAction.AMR_PROFILE: "[A]",
            AboutAction.KHADIGA_PROFILE: "[K]",
            AboutAction.REPOSITORY: "[Repo]",
            AboutAction.RETURN: "<-",
        }

    content: list[tuple[str, str]] = [
        (f"fg:{theme.identity} bold", "ShellPa links\n\n")
    ]
    for index, action in enumerate(ABOUT_ORDER):
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
        content.append((style, f"  {marker} {icons[action]} {labels[action]}\n"))
    content.append(
        (f"fg:{theme.muted}", "\nUp/Down choose  ·  Enter open  ·  Esc return")
    )
    return FormattedText(content)


def select_about_action(
    settings: UXSettings,
    return_label: str,
    *,
    initial_action: AboutAction = AboutAction.AMR_PROFILE,
    input_stream=None,
    output_stream=None,
) -> AboutAction:
    selected_index = [ABOUT_ORDER.index(initial_action)]
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: _about_selector_content(
            selected_index,
            settings,
            return_label,
        ),
        focusable=True,
    )

    @bindings.add("up")
    def _previous(event) -> None:
        selected_index[0] = (selected_index[0] - 1) % len(ABOUT_ORDER)
        event.app.invalidate()

    @bindings.add("down")
    def _next(event) -> None:
        selected_index[0] = (selected_index[0] + 1) % len(ABOUT_ORDER)
        event.app.invalidate()

    @bindings.add("enter")
    def _apply(event) -> None:
        event.app.exit(result=ABOUT_ORDER[selected_index[0]])

    @bindings.add("escape")
    @bindings.add("c-c")
    def _return(event) -> None:
        event.app.exit(result=AboutAction.CANCEL)

    application: Application[AboutAction] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        input=input_stream,
        output=output_stream,
    )
    return application.run()


def run_about_menu(
    console: Console,
    settings: UXSettings,
    *,
    return_label: str,
    opener=webbrowser.open,
    input_stream=None,
    output_stream=None,
) -> AboutAction | None:
    """Display shared About content and optionally open one selected URL."""
    display_about(console, settings)
    if input_stream is None and not console.is_terminal:
        console.print(f"[dim]AMR: {AMR_GITHUB_URL}[/dim]")
        console.print(f"[dim]KHADIGA: {KHADIGA_GITHUB_URL}[/dim]")
        console.print(f"[dim]Repository: {SHELLPA_REPOSITORY_URL}[/dim]")
        return None

    current_action = AboutAction.AMR_PROFILE
    while True:
        action = select_about_action(
            settings,
            return_label,
            initial_action=current_action,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        if action in {AboutAction.RETURN, AboutAction.CANCEL}:
            return action

        current_action = action
        url = ABOUT_URLS[action]
        try:
            opened = opener(url)
        except (OSError, webbrowser.Error) as exc:
            console.print(f"[yellow]ShellPa could not open the browser: {exc}[/yellow]")
            continue

        if opened is False:
            console.print(
                "[yellow]The browser did not accept the request. "
                f"Open this URL manually: {url}[/yellow]"
            )
            continue

        console.print(
            f"{ui_icon('success')} [green]Opened in your browser.[/green] "
            f"[dim]{url}[/dim]"
        )
