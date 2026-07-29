from unittest.mock import Mock

from typer.testing import CliRunner

from shellpa import main

runner = CliRunner()


def test_help_lists_public_commands() -> None:
    result = runner.invoke(main.app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "run",
        "config",
        "doctor",
        "context",
        "about",
        "help",
        "version",
    ):
        assert command in result.stdout


def test_help_command_prints_group_help() -> None:
    result = runner.invoke(main.app, ["help"])

    assert result.exit_code == 0
    assert "Commands" in result.stdout
    assert "doctor" in result.stdout


def test_version_command() -> None:
    result = runner.invoke(main.app, ["version"])

    assert result.exit_code == 0
    assert main.__version__ in result.stdout


def test_unknown_first_word_is_treated_as_natural_language(monkeypatch) -> None:
    run_shellpa = Mock()
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["show", "the", "files", "--dry-run"])

    assert result.exit_code == 0
    run_shellpa.assert_called_once()
    query, options = run_shellpa.call_args.args[0], run_shellpa.call_args.kwargs
    assert query == "show the files"
    assert options["dry_run"] is True


def test_global_options_reach_natural_language_fallback(monkeypatch) -> None:
    run_shellpa = Mock()
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["--mode", "plan", "show", "the", "files"])

    assert result.exit_code == 0
    assert run_shellpa.call_args.args[0] == "show the files"
    assert run_shellpa.call_args.kwargs["mode"] == "plan"


def test_run_allows_query_starting_with_reserved_word(monkeypatch) -> None:
    run_shellpa = Mock()
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["run", "config", "files"])

    assert result.exit_code == 0
    assert run_shellpa.call_args.args[0] == "config files"


def test_config_runs_wizard_without_starting_shell(monkeypatch) -> None:
    wizard = Mock()
    run_shellpa = Mock()
    wizard.return_value = True
    monkeypatch.setattr(main, "run_setup_wizard", wizard)
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["config"])

    assert result.exit_code == 0
    wizard.assert_called_once_with()
    run_shellpa.assert_not_called()


def test_doctor_runs_diagnostics_without_starting_shell(monkeypatch) -> None:
    report = Mock(exit_code=0)
    run_doctor = Mock(return_value=report)
    display_doctor = Mock()
    run_shellpa = Mock()
    monkeypatch.setattr(main, "run_doctor", run_doctor)
    monkeypatch.setattr(main, "display_doctor", display_doctor)
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["doctor"])

    assert result.exit_code == 0
    run_doctor.assert_called_once_with(online=False)
    display_doctor.assert_called_once_with(main.console, report)
    run_shellpa.assert_not_called()


def test_doctor_online_is_forwarded(monkeypatch) -> None:
    report = Mock(exit_code=0)
    run_doctor = Mock(return_value=report)
    monkeypatch.setattr(main, "run_doctor", run_doctor)
    monkeypatch.setattr(main, "display_doctor", Mock())

    result = runner.invoke(main.app, ["doctor", "--online"])

    assert result.exit_code == 0
    run_doctor.assert_called_once_with(online=True)


def test_context_is_offline_and_does_not_start_provider(monkeypatch) -> None:
    context = Mock()
    detect_workspace = Mock(return_value=context)
    display_workspace_context = Mock()
    run_shellpa = Mock()
    monkeypatch.setattr(main, "detect_workspace", detect_workspace)
    monkeypatch.setattr(
        main,
        "display_workspace_context",
        display_workspace_context,
    )
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["context"])

    assert result.exit_code == 0
    detect_workspace.assert_called_once_with()
    display_workspace_context.assert_called_once_with(main.console, context)
    run_shellpa.assert_not_called()


def test_about_stays_in_hub_until_user_leaves(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "run_about_menu",
        Mock(return_value=main.AboutAction.CANCEL),
    )
    run_shellpa = Mock()
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["about"])

    assert result.exit_code == 0
    run_shellpa.assert_not_called()


def test_about_can_return_to_interactive_shell(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "run_about_menu",
        Mock(return_value=main.AboutAction.RETURN),
    )
    run_shellpa = Mock()
    monkeypatch.setattr(main, "_run_shellpa", run_shellpa)

    result = runner.invoke(main.app, ["about"])

    assert result.exit_code == 0
    run_shellpa.assert_called_once()
    assert run_shellpa.call_args.args[0] is None
