"""Cross-platform process execution with streaming and bounded diagnostics."""

from __future__ import annotations

import locale
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Protocol, TextIO

from rich.console import Console

from .models import ExecutionRequest, ExecutionResult

console = Console()

STREAM_END = object()


class ExecutionObserver(Protocol):
    def start(self, command: str) -> None: ...

    def before_output(self) -> None: ...

    def finish(self) -> None: ...


class BoundedTextBuffer:
    """Retain only the newest diagnostic characters up to a fixed limit."""

    def __init__(self, limit: int):
        self.limit = limit
        self._value = ""
        self.truncated = False

    def append(self, text: str) -> None:
        if not text:
            return
        self._value += text
        if len(self._value) > self.limit:
            self._value = self._value[-self.limit :]
            self.truncated = True

    @property
    def value(self) -> str:
        return self._value


def build_shell_invocation(request: ExecutionRequest) -> list[str]:
    """Build an explicit shell wrapper for the requested platform."""
    if request.operating_system.lower() == "windows":
        if request.shell.lower() in {"powershell", "pwsh"}:
            executable = (
                "pwsh.exe" if request.shell.lower() == "pwsh" else "powershell.exe"
            )
            return [executable, "-NoProfile", "-Command", request.command]
        return ["cmd.exe", "/d", "/c", request.command]

    executable = "/bin/sh"
    if request.shell.lower() == "zsh":
        executable = "/bin/zsh"
    elif request.shell.lower() == "bash":
        executable = "/bin/bash"
    elif request.shell.lower() == "fish":
        executable = "/usr/bin/fish"
    return [executable, "-c", request.command]


def _subprocess_environment(request: ExecutionRequest) -> dict[str, str]:
    """Create a minimal inherited environment based on approved variable names."""
    if not request.environment_allowlist:
        return os.environ.copy()
    return {
        name: value
        for name, value in os.environ.items()
        if name in request.environment_allowlist
    }


def _process_group_options() -> dict:
    if os.name == "nt":
        creation_flag = getattr(  # noqa: B009
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
        )
        return {"creationflags": creation_flag}
    return {"start_new_session": True}


def _stream_reader(
    stream_name: str,
    stream: TextIO,
    events: queue.Queue[tuple[str, str | object]],
) -> None:
    try:
        for text in iter(stream.readline, ""):
            events.put((stream_name, text))
    finally:
        events.put((stream_name, STREAM_END))
        stream.close()


def _write_stream(
    stream_name: str,
    text: str,
    observer: ExecutionObserver | None = None,
) -> None:
    if observer is not None:
        observer.before_output()
    destination = sys.stdout if stream_name == "stdout" else sys.stderr
    destination.write(text)
    destination.flush()


def _terminate_process(process: subprocess.Popen, grace_seconds: float = 1.0) -> None:
    if process.poll() is not None:
        return

    try:
        if os.name != "nt":
            kill_process_group = getattr(os, "killpg")  # noqa: B009
            kill_process_group(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=grace_seconds)
        return
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        pass

    try:
        if os.name != "nt":
            kill_process_group = getattr(os, "killpg")  # noqa: B009
            kill_process_group(
                process.pid,
                getattr(signal, "SIGKILL"),  # noqa: B009
            )
        else:
            process.kill()
        process.wait(timeout=grace_seconds)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        pass


def _run_captured(
    process: subprocess.Popen,
    request: ExecutionRequest,
    started_at: float,
    observer: ExecutionObserver | None = None,
) -> ExecutionResult:
    stdout_buffer = BoundedTextBuffer(request.capture_limit_chars)
    stderr_buffer = BoundedTextBuffer(request.capture_limit_chars)
    events: queue.Queue[tuple[str, str | object]] = queue.Queue()
    completed_streams: set[str] = set()
    timed_out = False
    cancelled = False

    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Captured execution requires stdout and stderr pipes.")

    readers = [
        threading.Thread(
            target=_stream_reader,
            args=("stdout", process.stdout, events),
            daemon=True,
        ),
        threading.Thread(
            target=_stream_reader,
            args=("stderr", process.stderr, events),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    try:
        while len(completed_streams) < 2 or process.poll() is None:
            elapsed = time.monotonic() - started_at
            if (
                request.timeout_seconds is not None
                and elapsed >= request.timeout_seconds
            ):
                timed_out = True
                _terminate_process(process)

            try:
                stream_name, payload = events.get(timeout=0.05)
            except queue.Empty:
                if timed_out and process.poll() is not None:
                    continue
                continue

            if payload is STREAM_END:
                completed_streams.add(stream_name)
                continue

            text = str(payload)
            _write_stream(stream_name, text, observer)
            if stream_name == "stdout":
                stdout_buffer.append(text)
            else:
                stderr_buffer.append(text)
    except KeyboardInterrupt:
        cancelled = True
        _terminate_process(process)
        if observer is not None:
            observer.before_output()
        console.print("\n[yellow]Cancellation requested. Process stopped.[/yellow]")
    finally:
        for reader in readers:
            reader.join(timeout=1.0)

    return_code = process.poll()
    if return_code is None:
        try:
            return_code = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            return_code = process.poll()

    duration = time.monotonic() - started_at
    success = return_code == 0 and not timed_out and not cancelled
    return ExecutionResult(
        success=success,
        exit_code=return_code,
        stdout=stdout_buffer.value,
        stderr=stderr_buffer.value,
        duration_seconds=duration,
        timed_out=timed_out,
        cancelled=cancelled,
        output_truncated=stdout_buffer.truncated or stderr_buffer.truncated,
        partial_effect_possible=not success,
    )


def _run_passthrough(
    process: subprocess.Popen,
    request: ExecutionRequest,
    started_at: float,
    observer: ExecutionObserver | None = None,
) -> ExecutionResult:
    timed_out = False
    cancelled = False
    return_code: int | None = None

    if observer is not None:
        observer.before_output()
    try:
        return_code = process.wait(timeout=request.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process(process)
        return_code = process.poll()
    except KeyboardInterrupt:
        cancelled = True
        _terminate_process(process)
        return_code = process.poll()
        console.print("\n[yellow]Cancellation requested. Process stopped.[/yellow]")

    success = return_code == 0 and not timed_out and not cancelled
    return ExecutionResult(
        success=success,
        exit_code=return_code,
        duration_seconds=time.monotonic() - started_at,
        timed_out=timed_out,
        cancelled=cancelled,
        partial_effect_possible=not success,
    )


def execute_command(
    request: ExecutionRequest,
    observer: ExecutionObserver | None = None,
) -> ExecutionResult:
    """Execute an approved request and return a structured process result."""
    invocation = build_shell_invocation(request)
    started_at = time.monotonic()
    if observer is not None:
        observer.start(request.command)

    popen_options = {
        "cwd": request.working_directory,
        "env": _subprocess_environment(request),
        "text": True,
        "encoding": locale.getpreferredencoding(False),
        "errors": "replace",
        **_process_group_options(),
    }
    if not request.interactive:
        popen_options.update(
            {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 1,
            }
        )

    try:
        process = subprocess.Popen(invocation, **popen_options)
    except (OSError, ValueError) as exc:
        if observer is not None:
            observer.finish()
        return ExecutionResult(
            success=False,
            stderr=f"Failed to start command: {exc}",
            duration_seconds=time.monotonic() - started_at,
            partial_effect_possible=False,
        )

    try:
        if request.interactive:
            return _run_passthrough(process, request, started_at, observer)
        return _run_captured(process, request, started_at, observer)
    finally:
        if observer is not None:
            observer.finish()


def result_error_message(result: ExecutionResult) -> str:
    """Return a concise diagnostic message for UI and recovery."""
    if result.cancelled:
        return "Command cancelled by user."
    if result.timed_out:
        return "Command timed out."
    if result.stderr.strip():
        return result.stderr.strip()
    if result.stdout.strip():
        return result.stdout.strip()
    if result.exit_code is not None:
        return f"Failed with exit code {result.exit_code}."
    return "Command failed before an exit code was available."
