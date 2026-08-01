"""ShellPa-native text and secret entry with explicit navigation outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from .ux import UXSettings, active_theme, prompt_style


class InputAction(str, Enum):
    SUBMIT = "submit"
    BACK = "back"
    CANCEL = "cancel"


@dataclass(frozen=True)
class InputResult:
    action: InputAction
    value: str | None = field(default=None, repr=False)


def prompt_input(
    title: str,
    settings: UXSettings,
    *,
    description: str = "",
    secret: bool = False,
    input_stream=None,
    output_stream=None,
) -> InputResult:
    """Collect one non-empty value while keeping Back and Cancel distinct."""
    theme = active_theme(settings)
    error = [""]
    field = TextArea(
        height=1,
        multiline=False,
        password=secret,
        prompt=">_  ",
        style="class:prompt",
    )
    bindings = KeyBindings()

    def heading() -> FormattedText:
        content: list[tuple[str, str]] = [(f"fg:{theme.identity} bold", f"{title}\n")]
        if description:
            content.append((f"fg:{theme.muted}", f"{description}\n"))
        if error[0]:
            content.append((f"fg:{theme.danger} bold", f"{error[0]}\n"))
        return FormattedText(content)

    @bindings.add("enter")
    def _submit(event) -> None:
        value = field.text.strip()
        if not value:
            error[0] = "A value is required."
            event.app.invalidate()
            return
        event.app.exit(result=InputResult(InputAction.SUBMIT, value))

    @bindings.add("escape")
    def _back(event) -> None:
        event.app.exit(result=InputResult(InputAction.BACK))

    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=InputResult(InputAction.CANCEL))

    controls = FormattedTextControl(
        text=lambda: FormattedText(
            [
                (
                    f"fg:{theme.muted}",
                    "Enter continue  ·  Esc back  ·  Ctrl+C cancel setup",
                )
            ]
        )
    )
    application: Application[InputResult] = Application(
        layout=Layout(
            HSplit(
                [
                    Window(FormattedTextControl(text=heading)),
                    field,
                    Window(height=1, content=controls),
                ]
            ),
            focused_element=field,
        ),
        key_bindings=bindings,
        style=prompt_style(settings),
        full_screen=False,
        erase_when_done=True,
        input=input_stream,
        output=output_stream,
    )
    return application.run()
