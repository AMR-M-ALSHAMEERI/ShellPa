import io

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import shellpa.activity as activity
from shellpa.ux import UXSettings


def test_standard_approval_defaults_to_no_on_enter() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\r")
        approved = activity.select_standard_approval(
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert approved is False


def test_standard_approval_accepts_explicit_y() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("y")
        approved = activity.select_standard_approval(
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert approved is True


def test_first_time_onboarding_advances_and_marks_complete() -> None:
    settings = UXSettings()
    console = Console(file=io.StringIO(), force_terminal=False)

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\r\r\r")
        displayed = activity.run_first_time_onboarding(
            console,
            settings,
            input_stream=pipe_input,
            output_stream=DummyOutput(),
            persist=False,
        )

    assert displayed is True
    assert settings.onboarding_complete is True
    assert (
        activity.run_first_time_onboarding(
            console,
            settings,
            persist=False,
        )
        is False
    )


def test_activity_status_has_readable_nonanimated_fallback() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    with activity.activity_status(
        console,
        activity.ActivityState.GENERATING,
        UXSettings(animation="off"),
    ):
        pass

    assert "ShellPa" in output.getvalue()
    assert "Understanding your request" in output.getvalue()


def test_execution_activity_stops_animation_before_output() -> None:
    events = []

    class Status:
        def start(self):
            events.append("status-start")

        def stop(self):
            events.append("status-stop")

    class ConsoleStub:
        is_terminal = True

        def status(self, label, spinner):
            events.append("status-created")
            return Status()

        def print(self, value):
            events.append("print")

    observer = activity.ExecutionActivity(ConsoleStub(), UXSettings())
    observer.start("Get-Date")
    observer.before_output()
    observer.before_output()
    observer.finish()

    assert events == ["status-created", "status-start", "status-stop"]
