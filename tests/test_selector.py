from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

import shellpa.selector as selector
from shellpa.ux import UXSettings

OPTIONS = (
    selector.SelectionOption("ocean", "Ocean"),
    selector.SelectionOption("midnight", "Midnight Gold"),
)


def test_selector_renders_cursor_and_selected_value_independently(monkeypatch) -> None:
    monkeypatch.setattr(selector, "unicode_icons_supported", lambda: True)

    rendered = "".join(
        text
        for _, text in selector.selector_content(
            "Choose theme",
            OPTIONS,
            1,
            "ocean",
            UXSettings(),
        )
    )

    assert "● Ocean" in rendered
    assert "› ○ Midnight Gold" in rendered


def test_selector_marks_draft_change_once_in_heading(monkeypatch) -> None:
    monkeypatch.setattr(selector, "unicode_icons_supported", lambda: True)

    rendered = "".join(
        text
        for _, text in selector.selector_content(
            "Choose theme",
            OPTIONS,
            1,
            "midnight",
            UXSettings(),
            persisted_value="ocean",
        )
    )

    assert "Choose theme  •" in rendered
    assert "Current" not in rendered
    assert "Pending" not in rendered


def test_selector_distinguishes_select_back_and_cancel() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        selected = selector.select_interactively(
            "Choose theme",
            OPTIONS,
            "ocean",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert selected == selector.SelectorResult(
        selector.SelectorAction.SELECT,
        "midnight",
    )

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b")
        back = selector.select_interactively(
            "Choose theme",
            OPTIONS,
            "ocean",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert back.action is selector.SelectorAction.BACK

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x03")
        cancelled = selector.select_interactively(
            "Choose theme",
            OPTIONS,
            "ocean",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert cancelled.action is selector.SelectorAction.CANCEL
