from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from shellpa.input_ui import InputAction, prompt_input
from shellpa.ux import UXSettings


def test_text_entry_distinguishes_submit_back_and_cancel() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("custom/model\r")
        submitted = prompt_input(
            "Custom model",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert submitted.action is InputAction.SUBMIT
    assert submitted.value == "custom/model"

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b")
        back = prompt_input(
            "Custom model",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert back.action is InputAction.BACK

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x03")
        cancelled = prompt_input(
            "API key",
            UXSettings(),
            secret=True,
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert cancelled.action is InputAction.CANCEL


def test_secret_result_repr_does_not_expose_value() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("private-value\r")
        result = prompt_input(
            "API key",
            UXSettings(),
            secret=True,
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert "private-value" not in repr(result)
