from pathlib import Path

import pytest
from rich.console import Console

import shellpa.recovery as recovery
from shellpa.models import ExecutionRequest, ExecutionResult


def test_redact_sensitive_text_hides_common_secret_shapes(
    monkeypatch,
) -> None:
    monkeypatch.setattr(recovery.Path, "home", lambda: Path("C:/Users/Alice"))
    text = (
        "OPENAI_API_KEY=sk-secretvalue123 "
        "Authorization: Bearer abc.def-123 "
        "token ghp_1234567890abcdef "
        "url https://alice:password@example.com/path "
        "file C:/Users/Alice/project"
    )

    redacted = recovery.redact_sensitive_text(text)

    assert "secretvalue" not in redacted
    assert "abc.def" not in redacted
    assert "1234567890abcdef" not in redacted
    assert ":password@" not in redacted
    assert "C:/Users/Alice" not in redacted
    assert "<REDACTED>" in redacted
    assert "~/project" in redacted


def test_build_recovery_context_preserves_structured_status_and_redacts() -> None:
    request = ExecutionRequest(
        command="curl -H TOKEN=my-command-secret example",
        operating_system="Linux",
        shell="bash",
        working_directory=Path("/work"),
        attempt=2,
    )
    result = ExecutionResult(
        success=False,
        exit_code=22,
        stderr="TOKEN=my-secret-token",
        timed_out=False,
        output_truncated=True,
        partial_effect_possible=True,
    )

    context = recovery.build_recovery_context("call service", request, result)

    assert context.exit_code == 22
    assert context.attempt == 2
    assert context.output_truncated is True
    assert context.partial_effect_possible is True
    assert "my-secret-token" not in context.error_message
    assert "my-command-secret" not in context.failed_command
    assert context.sensitive_data_redacted is True


class Answer:
    def __init__(self, values: list[str]):
        self.values = iter(values)

    def ask(self) -> str:
        return next(self.values)


def test_recovery_permission_can_show_redacted_payload_then_allow_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = recovery.RecoveryContext(
        original_query="list files",
        failed_command="invalid-list",
        error_message="command not found",
        exit_code=127,
        attempt=1,
    )
    answer = Answer(["view", "once"])
    monkeypatch.setattr(
        recovery.questionary,
        "select",
        lambda *args, **kwargs: answer,
    )
    output = Console(force_terminal=False)

    assert recovery.request_recovery_permission(
        output,
        context,
        "openai",
        interactive=True,
    )


def test_noninteractive_recovery_fails_closed_without_prior_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHELLPA_RECOVERY_PERMISSION", raising=False)
    context = recovery.RecoveryContext(
        original_query="list files",
        failed_command="invalid-list",
        error_message="command not found",
        exit_code=127,
        attempt=1,
    )

    assert not recovery.request_recovery_permission(
        Console(force_terminal=False),
        context,
        "openai",
        interactive=False,
    )


def test_prior_allow_is_overridden_when_redaction_was_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHELLPA_RECOVERY_PERMISSION", "allow")
    context = recovery.RecoveryContext(
        original_query="call service",
        failed_command="curl TOKEN=<REDACTED>",
        error_message="failed",
        exit_code=1,
        attempt=1,
        sensitive_data_redacted=True,
    )
    monkeypatch.setattr(
        recovery.questionary,
        "select",
        lambda *args, **kwargs: Answer(["stop"]),
    )

    assert not recovery.request_recovery_permission(
        Console(force_terminal=False),
        context,
        "openai",
        interactive=True,
    )


def test_global_off_overrides_provider_allow() -> None:
    permission = recovery.configured_recovery_permission(
        "openai",
        {
            "SHELLPA_RECOVERY_PERMISSION": "off",
            "SHELLPA_RECOVERY_PERMISSION_OPENAI": "allow",
        },
    )

    assert permission is recovery.RecoveryPermission.OFF
