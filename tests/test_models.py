from pathlib import Path

import pytest
from pydantic import ValidationError

from shellpa.models import (
    CommandProposal,
    ConfirmationRequirement,
    ExecutionRequest,
    ExecutionResult,
    RecoveryContext,
    RiskAssessment,
    RiskLevel,
)


def test_command_proposal_strips_required_text() -> None:
    proposal = CommandProposal(
        command="  Get-ChildItem  ", explanation="  List files.  "
    )

    assert proposal.command == "Get-ChildItem"
    assert proposal.explanation == "List files."


def test_command_proposal_rejects_blank_command() -> None:
    with pytest.raises(ValidationError):
        CommandProposal(command="   ", explanation="Nothing")


def test_risk_assessment_has_safe_independent_defaults() -> None:
    first = RiskAssessment()
    second = RiskAssessment()
    first.reasons.append("example")

    assert first.risk_level is RiskLevel.UNKNOWN
    assert first.required_confirmation is ConfirmationRequirement.STANDARD
    assert second.reasons == []


def test_execution_request_validates_timeout_and_attempt() -> None:
    request = ExecutionRequest(
        command="echo ready",
        operating_system="Windows",
        shell="powershell",
        working_directory=Path("."),
        timeout_seconds=5,
    )

    assert request.attempt == 1
    assert request.timeout_seconds == 5

    with pytest.raises(ValidationError):
        ExecutionRequest(
            command="echo ready",
            operating_system="Windows",
            shell="powershell",
            working_directory=Path("."),
            timeout_seconds=0,
        )


def test_execution_result_records_process_state() -> None:
    result = ExecutionResult(
        success=False,
        exit_code=7,
        stderr="controlled failure",
        duration_seconds=0.25,
        partial_effect_possible=True,
    )

    assert result.exit_code == 7
    assert result.stderr == "controlled failure"
    assert result.partial_effect_possible is True


def test_recovery_context_records_failure_facts() -> None:
    context = RecoveryContext(
        original_query="list files",
        failed_command="invalid-list",
        error_message="command not found",
        exit_code=127,
        working_directory=Path("."),
        attempt=1,
        partial_effect_possible=True,
    )

    assert context.exit_code == 127
    assert context.partial_effect_possible is True
