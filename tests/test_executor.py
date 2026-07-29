import io
import subprocess
from pathlib import Path

import pytest

import shellpa.executor as executor
from shellpa.models import ExecutionRequest, ExecutionResult


class FakeProcess:
    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = 0,
        wait_timeout: bool = False,
    ):
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.returncode = returncode
        self.pid = 1234
        self.wait_timeout = wait_timeout
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout=None) -> int | None:
        if self.wait_timeout and not self.terminated and not self.killed:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 1

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1


def request(**overrides) -> ExecutionRequest:
    values = {
        "command": "Write-Output ready",
        "operating_system": "Windows",
        "shell": "powershell",
        "working_directory": Path("."),
    }
    values.update(overrides)
    return ExecutionRequest(**values)


def test_bounded_buffer_keeps_newest_text() -> None:
    buffer = executor.BoundedTextBuffer(5)
    buffer.append("abc")
    buffer.append("def")

    assert buffer.value == "bcdef"
    assert buffer.truncated is True


@pytest.mark.parametrize(
    ("execution_request", "expected"),
    [
        (
            request(),
            ["powershell.exe", "-NoProfile", "-Command", "Write-Output ready"],
        ),
        (
            request(shell="pwsh"),
            ["pwsh.exe", "-NoProfile", "-Command", "Write-Output ready"],
        ),
        (
            request(shell="cmd"),
            ["cmd.exe", "/d", "/c", "Write-Output ready"],
        ),
        (
            request(
                operating_system="Linux",
                shell="bash",
                command="printf ready",
            ),
            ["/bin/bash", "-c", "printf ready"],
        ),
        (
            request(
                operating_system="macOS",
                shell="zsh",
                command="printf ready",
            ),
            ["/bin/zsh", "-c", "printf ready"],
        ),
        (
            request(
                operating_system="Linux",
                shell="fish",
                command="printf ready",
            ),
            ["/usr/bin/fish", "-c", "printf ready"],
        ),
    ],
)
def test_build_shell_invocation(
    execution_request: ExecutionRequest,
    expected: list[str],
) -> None:
    assert executor.build_shell_invocation(execution_request) == expected


def test_execute_command_streams_and_captures_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess(stdout="ready\n", stderr="warning\n")

    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)
    result = executor.execute_command(request())

    streams = capsys.readouterr()
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == "ready\n"
    assert result.stderr == "warning\n"
    assert "ready" in streams.out
    assert "warning" in streams.err
    assert captured["command"][0] == "powershell.exe"
    assert captured["kwargs"]["stdout"] is subprocess.PIPE
    assert captured["kwargs"]["stderr"] is subprocess.PIPE


def test_execute_command_notifies_observer_around_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []

    class Observer:
        def start(self, command):
            events.append(("start", command))

        def before_output(self):
            events.append(("output", None))

        def finish(self):
            events.append(("finish", None))

    monkeypatch.setattr(
        executor.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(stdout="ready\n"),
    )

    result = executor.execute_command(request(), observer=Observer())

    assert result.success is True
    assert events[0] == ("start", "Write-Output ready")
    assert ("output", None) in events
    assert events[-1] == ("finish", None)


def test_execute_command_reports_failure_and_partial_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(
            stderr="controlled failure\n", returncode=7
        ),
    )

    result = executor.execute_command(request(command="invalid-command"))

    assert result.success is False
    assert result.exit_code == 7
    assert result.stderr == "controlled failure\n"
    assert result.partial_effect_possible is True
    assert executor.result_error_message(result) == "controlled failure"


def test_execute_command_reports_start_failure_without_partial_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_start(*args, **kwargs):
        raise OSError("shell missing")

    monkeypatch.setattr(executor.subprocess, "Popen", fail_to_start)
    result = executor.execute_command(request())

    assert result.success is False
    assert "shell missing" in result.stderr
    assert result.exit_code is None
    assert result.partial_effect_possible is False


def test_execute_command_bounds_captured_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(stdout="x" * 1200),
    )
    result = executor.execute_command(request(capture_limit_chars=1000))

    assert len(result.stdout) == 1000
    assert result.output_truncated is True


def test_passthrough_inherits_terminal_and_honors_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = FakeProcess(returncode=None, wait_timeout=True)
    captured: dict = {}

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        return process

    monkeypatch.setattr(executor.subprocess, "Popen", fake_popen)
    result = executor.execute_command(request(interactive=True, timeout_seconds=0.1))

    assert "stdout" not in captured
    assert "stderr" not in captured
    assert result.timed_out is True
    assert result.success is False
    assert process.terminated is True


def test_result_error_message_uses_state_precedence() -> None:
    assert (
        executor.result_error_message(ExecutionResult(success=False, cancelled=True))
        == "Command cancelled by user."
    )
    assert (
        executor.result_error_message(ExecutionResult(success=False, timed_out=True))
        == "Command timed out."
    )
    assert (
        executor.result_error_message(ExecutionResult(success=False, exit_code=9))
        == "Failed with exit code 9."
    )
