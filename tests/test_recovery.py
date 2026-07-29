from pathlib import Path

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
        command="curl example",
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
