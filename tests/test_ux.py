import io
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

import shellpa.ux as ux
from shellpa.models import CommandProposal, ExecutionResult, RiskAssessment, RiskLevel


def test_load_ux_settings_uses_safe_defaults_for_missing_or_invalid_file(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    assert ux.load_ux_settings(missing) == ux.UXSettings()

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    assert ux.load_ux_settings(invalid) == ux.UXSettings()


def test_ux_settings_normalize_and_save_without_secrets(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    saved_path = ux.save_ux_settings(
        ux.UXSettings(theme="invalid", animation="invalid", reduced_motion=True),
        path,
    )

    payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert payload == {
        "theme": "ocean",
        "animation": "full",
        "reduced_motion": True,
        "onboarding_complete": False,
    }
    assert set(payload) == {
        "theme",
        "animation",
        "reduced_motion",
        "onboarding_complete",
    }


def test_no_color_selects_ansi_theme(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert ux.active_theme(ux.UXSettings(theme="ocean")).name == "ansi"


def test_all_themes_build_prompt_and_confirmation_styles() -> None:
    assert "aurora" in ux.THEMES
    for theme_name in ux.THEMES:
        settings = ux.UXSettings(theme=theme_name)
        assert ux.prompt_style(settings)
        assert ux.questionary_style(settings)


def test_animation_off_prints_nothing() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    ux.play_startup_reveal(
        console,
        ux.UXSettings(animation="off"),
        {"shell": "powershell"},
        "test-model",
        sleep=lambda _: None,
    )

    assert output.getvalue() == ""


def test_non_terminal_reveal_is_static_and_has_context() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=100)

    ux.play_startup_reveal(
        console,
        ux.UXSettings(animation="full"),
        {"shell": "powershell"},
        "test-model",
        sleep=lambda _: None,
    )

    rendered = output.getvalue()
    assert "Natural language. Native commands." in rendered
    assert "powershell" in rendered
    assert "test-model" in rendered


def test_session_greeting_is_time_aware_and_curated() -> None:
    greeting, statement = ux.session_greeting_copy(
        datetime(2026, 7, 29, 9, 0),
        statement_index=0,
    )

    assert greeting == "Good morning."
    assert statement == "What are we working on today?"
    assert statement in ux.SESSION_STATEMENTS


def test_session_greeting_is_hidden_outside_real_terminal() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    ux.display_session_greeting(
        console,
        ux.UXSettings(),
        now=datetime(2026, 7, 29, 18, 0),
        statement_index=0,
        sleep=lambda _: None,
    )

    assert output.getvalue() == ""


def test_reduced_motion_session_greeting_is_static_and_immediate() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=True)
    sleeps = []

    ux.display_session_greeting(
        console,
        ux.UXSettings(animation="compact", reduced_motion=True),
        now=datetime(2026, 7, 29, 18, 0),
        statement_index=0,
        sleep=sleeps.append,
    )

    rendered = output.getvalue()
    assert "Good evening." in rendered
    assert "What are we working on today?" in rendered
    assert sleeps == []


def test_proposal_review_answers_command_decision_questions() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=100)
    proposal = CommandProposal(
        command="Get-ChildItem",
        explanation="List project files.",
    )
    assessment = RiskAssessment(
        risk_level=RiskLevel.READ_ONLY,
        reasons=["Known read-only PowerShell command."],
        affected_targets=["C:\\project"],
    )

    ux.display_proposal_review(
        console,
        proposal,
        assessment,
        "powershell",
        ux.UXSettings(),
    )

    rendered = output.getvalue()
    assert "Get-ChildItem" in rendered
    assert "READ ONLY" in rendered
    assert "Purpose" in rendered
    assert "List project files." in rendered
    assert "Scope" in rendered
    assert "C:\\project" in rendered
    assert "Safety" in rendered


def test_failure_panel_treats_diagnostic_as_text_not_markup() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    ux.display_execution_failure(
        console,
        ExecutionResult(success=False, exit_code=7, duration_seconds=0.5),
        "[red]literal diagnostic[/red]",
        ux.UXSettings(),
    )

    assert "[red]literal diagnostic[/red]" in output.getvalue()


def test_about_panel_has_shared_identity_and_version() -> None:
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    ux.display_about(console, ux.UXSettings())

    rendered = output.getvalue()
    assert "About ShellPa" in rendered
    assert "ShellPa v" in rendered
    assert "Natural language. Native commands. Your authority." in rendered
    assert "AMR" in rendered
    assert "KHADIGA" in rendered
