import io
import urllib.error
from pathlib import Path

from rich.console import Console

import shellpa.diagnostics as diagnostics
from shellpa.codex_provider import CodexAccountState, CodexAccountStatus


def configured_environment() -> dict[str, str]:
    return {
        "SHELLPA_MODEL": "gpt-4o",
        "SHELLPA_PROVIDER": "openai",
        "OPENAI_API_KEY": "super-secret-value",
    }


def test_doctor_reports_configuration_without_exposing_secret(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "detect_environment",
        lambda: {"os": "Windows", "shell": "powershell"},
    )
    monkeypatch.setattr(
        diagnostics,
        "get_env_path",
        lambda: tmp_path / ".shellpa.env",
    )
    monkeypatch.setattr(
        diagnostics,
        "get_settings_path",
        lambda: tmp_path / "settings.json",
    )

    report = diagnostics.run_doctor(environ=configured_environment())
    combined = " ".join(
        f"{check.name} {check.detail} {check.remedy}" for check in report.checks
    )

    assert "Credential" in combined
    assert "value hidden" in combined
    assert "super-secret-value" not in combined


def test_online_doctor_treats_http_response_as_reachable(monkeypatch) -> None:
    def http_response(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )

    report = diagnostics.run_doctor(
        online=True,
        environ=configured_environment(),
        opener=http_response,
    )
    reachability = next(
        check for check in report.checks if check.name == "Provider reachability"
    )

    assert reachability.level is diagnostics.CheckLevel.PASS
    assert "no credential was sent" in reachability.detail


def test_online_doctor_reports_network_failure() -> None:
    def unavailable(request, timeout):
        raise urllib.error.URLError("offline")

    report = diagnostics.run_doctor(
        online=True,
        environ=configured_environment(),
        opener=unavailable,
    )
    reachability = next(
        check for check in report.checks if check.name == "Provider reachability"
    )

    assert reachability.level is diagnostics.CheckLevel.FAIL
    assert report.exit_code == 1


def test_doctor_display_has_pass_warn_fail_labels() -> None:
    report = diagnostics.DoctorReport(
        [
            diagnostics.DiagnosticCheck(
                "Ready",
                diagnostics.CheckLevel.PASS,
                "ready",
            ),
            diagnostics.DiagnosticCheck(
                "Optional",
                diagnostics.CheckLevel.WARN,
                "warning",
            ),
            diagnostics.DiagnosticCheck(
                "Broken",
                diagnostics.CheckLevel.FAIL,
                "failure",
                "repair it",
            ),
        ]
    )
    output = io.StringIO()
    diagnostics.display_doctor(
        Console(file=output, force_terminal=False, width=120),
        report,
    )

    rendered = output.getvalue()
    assert "PASS" in rendered
    assert "WARN" in rendered
    assert "FAIL" in rendered
    assert "repair it" in rendered


def test_doctor_reports_codex_sdk_and_chatgpt_status_without_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "inspect_codex_account",
        lambda: CodexAccountStatus(
            CodexAccountState.CHATGPT,
            plan_type="plus",
            detail="private@example.com",
        ),
    )
    report = diagnostics.run_doctor(
        environ={
            "SHELLPA_PROVIDER": "codex",
            "SHELLPA_MODEL": "codex/default",
        }
    )
    combined = " ".join(check.detail for check in report.checks)

    assert "embedded Codex SDK" in combined
    assert "ChatGPT account connected (plus)" in combined
    assert "private@example.com" not in combined
