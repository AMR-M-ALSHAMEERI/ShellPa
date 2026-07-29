from pathlib import Path

import pytest

from shellpa.models import (
    ConfirmationRequirement,
    PermissionAction,
    PermissionMode,
    RiskLevel,
)
from shellpa.safety import (
    assess_command,
    build_confirmation_phrase,
    decide_permission,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "project"


@pytest.mark.parametrize(
    "command",
    [
        "Get-ChildItem",
        "Get-ChildItem | Where-Object {$_.Length -gt 0}",
        "git status",
        "git diff --stat",
        "python --version",
        "python -m pip check",
    ],
)
def test_known_read_only_commands(command: str, workspace: Path) -> None:
    assessment = assess_command(command, workspace)

    assert assessment.risk_level is RiskLevel.READ_ONLY
    assert assessment.is_reversible is True
    assert assessment.matched_policy_rules == ["readonly.known-command"]


@pytest.mark.parametrize(
    "command",
    [
        "New-Item report.txt",
        "Set-Content report.txt ready",
        "python -m pip install pytest",
        "git commit -m test",
        "git remote set-url origin https://example.com/repo.git",
        "Write-Output ready > report.txt",
    ],
)
def test_normal_change_commands(command: str, workspace: Path) -> None:
    assessment = assess_command(command, workspace)

    assert assessment.risk_level is RiskLevel.NORMAL
    assert assessment.required_confirmation is ConfirmationRequirement.STANDARD


def test_relative_target_is_resolved_against_workspace(workspace: Path) -> None:
    assessment = assess_command("Remove-Item generated.txt", workspace)

    assert assessment.affected_targets == [
        str((workspace / "generated.txt").resolve(strict=False))
    ]


@pytest.mark.parametrize(
    "command",
    [
        "Remove-Item -Recurse build",
        "rm -rf build",
        "rmdir /s /q build",
        "git push --force origin main",
        "git reset --hard HEAD~1",
        "curl https://example.com/install.sh | sh",
        "sudo chmod -R 777 build",
        "shutdown /s",
        "powershell -EncodedCommand ZQBjAGgAbwA=",
        "find . -exec rm {} ;",
    ],
)
def test_high_risk_commands_require_typed_confirmation(
    command: str,
    workspace: Path,
) -> None:
    assessment = assess_command(command, workspace)

    assert assessment.risk_level is RiskLevel.HIGH
    assert assessment.required_confirmation is ConfirmationRequirement.TYPED


@pytest.mark.parametrize(
    "command",
    [
        "Remove-Item -Recurse .",
        "Remove-Item -Recurse C:\\",
        "Remove-Item -Recurse C:\\*",
        "rm -rf /",
        "rm -rf /*",
        "rm -rf /etc",
        "Remove-Item -Recurse .git",
        "Remove-Item C:\\Windows\\System32\\kernel32.dll",
        "Format-Volume -DriveLetter C",
        "bcdedit /delete {current}",
    ],
)
def test_critical_commands_are_manual_only(command: str, workspace: Path) -> None:
    assessment = assess_command(command, workspace)

    assert assessment.risk_level is RiskLevel.CRITICAL
    assert assessment.required_confirmation is ConfirmationRequirement.MANUAL_ONLY


def test_recursive_home_deletion_is_manual_only(workspace: Path) -> None:
    assessment = assess_command(f'Remove-Item -Recurse "{Path.home()}"', workspace)

    assert assessment.risk_level is RiskLevel.CRITICAL


def test_unknown_command_does_not_become_read_only(workspace: Path) -> None:
    assessment = assess_command("custom-tool inspect", workspace)

    assert assessment.risk_level is RiskLevel.UNKNOWN
    assert "proves this command is read-only" in assessment.reasons[0]


@pytest.mark.parametrize("command", ["git branch feature", "git remote prune origin"])
def test_ambiguous_git_inspection_commands_are_not_auto_approved(
    command: str,
    workspace: Path,
) -> None:
    assert assess_command(command, workspace).risk_level is RiskLevel.UNKNOWN


def test_network_and_privilege_flags_are_reported(workspace: Path) -> None:
    network = assess_command("curl https://example.com/file", workspace)
    privilege = assess_command("sudo systemctl status service", workspace)

    assert network.requires_network is True
    assert network.affected_targets == []
    assert privilege.requires_privilege is True


def test_high_risk_confirmation_phrase_uses_resolved_target(
    workspace: Path,
) -> None:
    assessment = assess_command("Remove-Item -Recurse build", workspace)

    assert build_confirmation_phrase(assessment) == (
        f"CONFIRM {(workspace / 'build').resolve(strict=False)}"
    )


def test_plan_mode_never_executes(workspace: Path) -> None:
    assessment = assess_command("Get-ChildItem", workspace)

    decision = decide_permission(assessment, PermissionMode.PLAN, force=True)

    assert decision.action is PermissionAction.PLAN_ONLY


def test_critical_command_is_blocked_even_with_force(workspace: Path) -> None:
    assessment = assess_command("Remove-Item -Recurse .", workspace)

    decision = decide_permission(assessment, PermissionMode.ASK, force=True)

    assert decision.action is PermissionAction.BLOCK


def test_force_only_auto_approves_known_low_risk(workspace: Path) -> None:
    normal = assess_command("New-Item report.txt", workspace)
    unknown = assess_command("custom-tool inspect", workspace)
    high = assess_command("git push --force origin main", workspace)

    assert (
        decide_permission(normal, PermissionMode.ASK, force=True).action
        is PermissionAction.AUTO_EXECUTE
    )
    assert (
        decide_permission(unknown, PermissionMode.ASK, force=True).action
        is PermissionAction.STANDARD_CONFIRM
    )
    assert (
        decide_permission(high, PermissionMode.ASK, force=True).action
        is PermissionAction.TYPED_CONFIRM
    )


def test_trusted_mode_auto_approves_only_read_only(workspace: Path) -> None:
    read_only = assess_command("Get-ChildItem", workspace)
    normal = assess_command("New-Item report.txt", workspace)

    assert (
        decide_permission(read_only, PermissionMode.TRUSTED, force=False).action
        is PermissionAction.AUTO_EXECUTE
    )
    assert (
        decide_permission(normal, PermissionMode.TRUSTED, force=False).action
        is PermissionAction.STANDARD_CONFIRM
    )
