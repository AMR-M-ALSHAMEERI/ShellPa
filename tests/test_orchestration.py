from collections.abc import Iterator

import pytest

import shellpa.main as main
from shellpa.models import (
    CommandProposal,
    ExecutionResult,
    PermissionMode,
    RecoveryContext,
)


class Confirmation:
    def __init__(self, answers: Iterator[bool]):
        self._answers = answers

    def ask(self) -> bool:
        return next(self._answers)


class TextAnswer:
    def __init__(self, answer: str):
        self.answer = answer

    def ask(self) -> str:
        return self.answer


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event: str, **fields) -> bool:
        self.events.append((event, fields))
        return True


def test_dry_run_never_executes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )

    def fail_if_executed(*args, **kwargs):
        pytest.fail("dry-run attempted to execute a command")

    monkeypatch.setattr(main, "execute_command", fail_if_executed)

    main.process_query(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=True,
    )


def test_approved_command_executes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    answers = iter([True])
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: Confirmation(answers),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda request, observer=None: (
            executed.append(request.command)
            or ExecutionResult(success=True, exit_code=0)
        ),
    )

    main.process_query(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
    )

    assert executed == ["Get-Date"]


def test_recovery_proposal_is_confirmed_and_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    answers = iter([True, True, True])
    results = iter(
        [
            ExecutionResult(
                success=False,
                exit_code=127,
                stderr="command not found",
                partial_effect_possible=True,
            ),
            ExecutionResult(success=True, exit_code=0),
        ]
    )
    recovery_contexts: list[RecoveryContext] = []
    workspace_summaries: list[str | None] = []
    workspace_context = object()
    monkeypatch.setattr(
        main,
        "format_provider_workspace_summary",
        lambda context: "Project types: python\nGit: main",
    )

    def generate_initial(query, env_info, workspace_summary=None):
        workspace_summaries.append(workspace_summary)
        return CommandProposal(
            command="invalid-list",
            explanation="Attempt to list files.",
        )

    def generate_recovery(context, env_info, workspace_summary=None):
        recovery_contexts.append(context)
        workspace_summaries.append(workspace_summary)
        return CommandProposal(
            command="Get-ChildItem",
            explanation="Use the PowerShell command.",
        )

    monkeypatch.setattr(
        main,
        "generate_command",
        generate_initial,
    )
    monkeypatch.setattr(
        main,
        "generate_recovery_command",
        generate_recovery,
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: Confirmation(answers),
    )

    def fake_execute(request, observer=None):
        executed.append(request.command)
        return next(results)

    monkeypatch.setattr(main, "execute_command", fake_execute)

    main.process_query(
        "list files",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
        workspace_context=workspace_context,
    )

    assert executed == ["invalid-list", "Get-ChildItem"]
    assert workspace_summaries == [
        "Project types: python\nGit: main",
        "Project types: python\nGit: main",
    ]
    assert recovery_contexts[0].exit_code == 127
    assert recovery_contexts[0].error_message == "command not found"


def test_plan_mode_never_requests_permission_or_executes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: pytest.fail("plan mode requested confirmation"),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda *args, **kwargs: pytest.fail("plan mode executed a command"),
    )

    main.process_query(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
        force=True,
        dry_run=False,
        mode=PermissionMode.PLAN,
    )


def test_trusted_mode_executes_known_read_only_without_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: pytest.fail("trusted read-only command prompted"),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda request, observer=None: (
            executed.append(request.command)
            or ExecutionResult(success=True, exit_code=0)
        ),
    )

    main.process_query(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
        mode=PermissionMode.TRUSTED,
    )

    assert executed == ["Get-Date"]


def test_force_does_not_bypass_high_risk_typed_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="git push --force origin main",
            explanation="Rewrite remote history.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "text",
        lambda *args, **kwargs: TextAnswer("CONFIRM HIGH RISK"),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda request, observer=None: (
            executed.append(request.command)
            or ExecutionResult(success=True, exit_code=0)
        ),
    )

    main.process_query(
        "force push",
        {"os": "Windows", "shell": "powershell"},
        force=True,
        dry_run=False,
    )

    assert executed == ["git push --force origin main"]


def test_critical_command_is_never_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Remove-Item -Recurse .",
            explanation="Delete the current workspace.",
        ),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda *args, **kwargs: pytest.fail("critical command was executed"),
    )

    main.process_query(
        "delete this workspace",
        {"os": "Windows", "shell": "powershell"},
        force=True,
        dry_run=False,
    )


def test_recovery_command_receives_fresh_critical_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    answers = iter([True, True])
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="invalid-list",
            explanation="Attempt to list files.",
        ),
    )
    monkeypatch.setattr(
        main,
        "generate_recovery_command",
        lambda *args, **kwargs: CommandProposal(
            command="Remove-Item -Recurse .",
            explanation="Unsafe correction.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: Confirmation(answers),
    )

    def fake_execute(request, observer=None):
        executed.append(request.command)
        return ExecutionResult(
            success=False,
            exit_code=1,
            stderr="controlled failure",
            partial_effect_possible=True,
        )

    monkeypatch.setattr(main, "execute_command", fake_execute)

    main.process_query(
        "list files",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
    )

    assert executed == ["invalid-list"]


def test_cancelled_command_does_not_request_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = iter([True])
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: Confirmation(answers),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda request, observer=None: ExecutionResult(
            success=False,
            cancelled=True,
            partial_effect_possible=True,
        ),
    )
    monkeypatch.setattr(
        main,
        "generate_recovery_command",
        lambda *args, **kwargs: pytest.fail("cancelled command requested recovery"),
    )

    main.process_query(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
    )


def test_timeout_and_passthrough_are_forwarded_to_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )
    monkeypatch.setattr(
        main.questionary,
        "confirm",
        lambda *args, **kwargs: Confirmation(iter([True])),
    )

    def fake_execute(request, observer=None):
        requests.append(request)
        return ExecutionResult(success=True, exit_code=0)

    monkeypatch.setattr(main, "execute_command", fake_execute)

    main.process_query(
        "show the date",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
        timeout_seconds=3.5,
        passthrough=True,
    )

    assert requests[0].timeout_seconds == 3.5
    assert requests[0].interactive is True


def test_query_processing_logs_metadata_not_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    monkeypatch.setattr(
        main,
        "generate_command",
        lambda query, env_info, workspace_summary=None: CommandProposal(
            command="Get-Date",
            explanation="Show the date.",
        ),
    )
    monkeypatch.setattr(
        main,
        "execute_command",
        lambda request, observer=None: ExecutionResult(
            success=True,
            exit_code=0,
            duration_seconds=0.02,
        ),
    )

    main.process_query(
        "private request text",
        {"os": "Windows", "shell": "powershell"},
        force=False,
        dry_run=False,
        mode=PermissionMode.TRUSTED,
        event_logger=logger,
    )

    names = [name for name, _ in logger.events]
    assert names == [
        "generation_completed",
        "risk_assessed",
        "execution_completed",
    ]
    serialized = repr(logger.events)
    assert "private request text" not in serialized
    assert "Get-Date" not in serialized
