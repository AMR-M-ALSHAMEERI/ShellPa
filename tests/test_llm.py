from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import shellpa.llm as llm
from shellpa.models import CommandProposal, RecoveryContext


def fake_response(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.parametrize(
    "content",
    [
        '{"command":"Get-ChildItem","explanation":"List files."}',
        '```json\n{"command":"Get-ChildItem","explanation":"List files."}\n```',
        '```json {"command":"Get-ChildItem","explanation":"List files."} ```',
        '```\n{"command":"Get-ChildItem","explanation":"List files."}\n```',
    ],
)
def test_parse_command_response_accepts_plain_and_fenced_json(content: str) -> None:
    proposal = llm.parse_command_response(content)

    assert proposal == CommandProposal(
        command="Get-ChildItem",
        explanation="List files.",
    )


def test_parse_command_response_rejects_blank_fields() -> None:
    with pytest.raises(ValidationError):
        llm.parse_command_response('{"command":" ","explanation":"List files."}')


def test_generate_command_uses_configured_model_and_validates_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return fake_response('{"command":"Get-Date","explanation":"Show the date."}')

    monkeypatch.setattr(llm, "completion", fake_completion)
    monkeypatch.setenv("SHELLPA_MODEL", "test/provider-model")

    proposal = llm.generate_command(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
    )

    assert proposal.command == "Get-Date"
    assert captured["model"] == "test/provider-model"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][-1]["content"] == "show the date"


def test_generate_recovery_includes_failure_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return fake_response(
            '{"command":"Get-ChildItem","explanation":"Use the correct command."}'
        )

    monkeypatch.setattr(llm, "completion", fake_completion)

    proposal = llm.generate_recovery_command(
        RecoveryContext(
            original_query="list files",
            failed_command="invalid-list",
            error_message="command not found",
            exit_code=127,
            working_directory=Path("C:/work"),
            attempt=1,
            partial_effect_possible=True,
        ),
        {"os": "Windows", "shell": "powershell"},
    )

    user_content = captured["messages"][-1]["content"]
    assert proposal.command == "Get-ChildItem"
    assert "invalid-list" in user_content
    assert "command not found" in user_content
    assert "127" in user_content
    assert "partially changed" in user_content.lower()


def test_request_command_rejects_empty_provider_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "completion", lambda **kwargs: fake_response(None))

    with pytest.raises(ValueError, match="empty command response"):
        llm.generate_command("list files", {"os": "Windows", "shell": "powershell"})
