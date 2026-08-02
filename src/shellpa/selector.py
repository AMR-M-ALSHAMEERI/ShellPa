"""Reusable ShellPa-native single-choice terminal selector."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from .icons import unicode_icons_supported
from .ux import UXSettings, active_theme

T = TypeVar("T")


@dataclass(frozen=True)
class SelectionOption(Generic[T]):
    value: T
    label: str
    description: str = ""


class SelectorAction(str, Enum):
    SELECT = "select"
    BACK = "back"
    CANCEL = "cancel"


@dataclass(frozen=True)
class SelectorResult(Generic[T]):
    action: SelectorAction
    value: T | None = None


def selector_content(
    title: str,
    options: Sequence[SelectionOption[T]],
    focused_index: int,
    selected_value: T,
    settings: UXSettings,
    *,
    persisted_value: T | None = None,
    preview: Callable[[T, UXSettings], FormattedText] | None = None,
    allow_back: bool = True,
) -> FormattedText:
    """Render focus and selected state independently."""
    theme = active_theme(settings)
    unicode = unicode_icons_supported()
    changed = persisted_value is not None and selected_value != persisted_value
    heading_suffix = "  •" if changed and unicode else "  *" if changed else ""
    content: list[tuple[str, str]] = [
        (f"fg:{theme.identity} bold", f"{title}{heading_suffix}\n\n")
    ]
    for index, option in enumerate(options):
        focused = index == focused_index
        cursor = ("›" if unicode else ">") if focused else " "
        marker = (
            ("●" if unicode else "[x]")
            if option.value == selected_value
            else ("○" if unicode else "[ ]")
        )
        style = f"fg:{theme.identity} bold reverse" if focused else f"fg:{theme.muted}"
        content.append((style, f" {cursor} {marker} {option.label}\n"))

    focused_option = options[focused_index]
    if focused_option.description:
        content.extend(
            [
                ("", "\n"),
                (f"fg:{theme.accent}", f"{focused_option.description}\n"),
            ]
        )
    if preview is not None:
        content.append(("", "\n"))
        for item in preview(focused_option.value, settings):
            content.append((item[0], item[1]))

    controls = "Up/Down inspect  ·  Enter select"
    if allow_back:
        controls += "  ·  Esc back"
    controls += "  ·  Ctrl+C cancel"
    content.extend([("", "\n"), (f"fg:{theme.muted}", controls)])
    return FormattedText(content)


def select_interactively(
    title: str,
    options: Sequence[SelectionOption[T]],
    selected_value: T,
    settings: UXSettings,
    *,
    persisted_value: T | None = None,
    preview: Callable[[T, UXSettings], FormattedText] | None = None,
    allow_back: bool = True,
    refresh_interval: float | None = None,
    input_stream=None,
    output_stream=None,
) -> SelectorResult[T]:
    """Run a selector with stable Back and Cancel semantics."""
    if not options:
        raise ValueError("A selector requires at least one option.")
    values = [option.value for option in options]
    try:
        initial_index = values.index(selected_value)
    except ValueError:
        initial_index = 0
        selected_value = options[0].value
    focused_index = [initial_index]
    bindings = KeyBindings()
    control = FormattedTextControl(
        text=lambda: selector_content(
            title,
            options,
            focused_index[0],
            selected_value,
            settings,
            persisted_value=persisted_value,
            preview=preview,
            allow_back=allow_back,
        ),
        focusable=True,
    )

    @bindings.add("up")
    def _previous(event) -> None:
        focused_index[0] = (focused_index[0] - 1) % len(options)
        event.app.invalidate()

    @bindings.add("down")
    def _next(event) -> None:
        focused_index[0] = (focused_index[0] + 1) % len(options)
        event.app.invalidate()

    @bindings.add("enter")
    def _select(event) -> None:
        event.app.exit(
            result=SelectorResult(
                SelectorAction.SELECT,
                options[focused_index[0]].value,
            )
        )

    @bindings.add("escape")
    def _back(event) -> None:
        event.app.exit(
            result=SelectorResult(
                SelectorAction.BACK if allow_back else SelectorAction.CANCEL
            )
        )

    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=SelectorResult(SelectorAction.CANCEL))

    application: Application[SelectorResult[T]] = Application(
        layout=Layout(Window(content=control, always_hide_cursor=True)),
        key_bindings=bindings,
        full_screen=False,
        erase_when_done=True,
        refresh_interval=refresh_interval,
        input=input_stream,
        output=output_stream,
    )
    return application.run()
