from __future__ import annotations

import io
import subprocess
import sys
from dataclasses import dataclass

import pytest
from rich.console import Console

import shellpa.codex_install as codex_install
from shellpa.codex_provider import CODEX_SDK_REQUIREMENT


@dataclass
class Completed:
    returncode: int


def test_install_uses_active_interpreter_without_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> Completed:
        calls.append((command, kwargs))
        return Completed(returncode=0)

    monkeypatch.setattr(codex_install, "codex_sdk_installed", lambda: True)
    console = Console(file=io.StringIO(), force_terminal=False)

    assert codex_install.install_codex_sdk(console, runner=runner) is True
    assert calls == [
        (
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                CODEX_SDK_REQUIREMENT,
            ],
            {
                "check": False,
                "capture_output": True,
                "text": True,
                "shell": False,
            },
        )
    ]


def test_install_failure_gives_manual_recovery_command() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    assert (
        codex_install.install_codex_sdk(
            console,
            runner=lambda *args, **kwargs: Completed(returncode=7),
        )
        is False
    )

    rendered = output.getvalue()
    assert "exit code 7" in rendered
    assert CODEX_SDK_REQUIREMENT in rendered


def test_install_handles_process_start_failure() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    def fail(*args: object, **kwargs: object) -> Completed:
        raise subprocess.SubprocessError("pip unavailable")

    assert codex_install.install_codex_sdk(console, runner=fail) is False
    assert "SubprocessError" in output.getvalue()


def test_install_verifies_the_sdk_can_be_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    monkeypatch.setattr(codex_install, "codex_sdk_installed", lambda: False)

    assert (
        codex_install.install_codex_sdk(
            console,
            runner=lambda *args, **kwargs: Completed(returncode=0),
        )
        is False
    )
    assert "could not import" in output.getvalue()
