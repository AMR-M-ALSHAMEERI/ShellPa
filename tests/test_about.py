import io

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import shellpa.about as about
from shellpa.ux import UXSettings


def test_about_urls_match_project_owners_and_repository() -> None:
    assert about.AMR_GITHUB_URL == "https://github.com/AMR-M-ALSHAMEERI"
    assert about.KHADIGA_GITHUB_URL == "https://github.com/doji0x0"
    assert about.SHELLPA_REPOSITORY_URL == "https://github.com/AMR-M-ALSHAMEERI/ShellPa"


def test_about_selector_can_choose_repository_with_keyboard() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\x1b[B\r")
        selected = about.select_about_action(
            UXSettings(),
            "Return to ShellPa",
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert selected is about.AboutAction.REPOSITORY


def test_about_selector_escape_cancels_without_selecting_launch() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b")
        selected = about.select_about_action(
            UXSettings(),
            "Launch ShellPa Interactive",
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert selected is about.AboutAction.CANCEL


def test_about_menu_opens_repository_then_stays_until_return(
    monkeypatch,
) -> None:
    opened = []
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    actions = iter([about.AboutAction.REPOSITORY, about.AboutAction.RETURN])
    selected_initial_actions = []

    def fake_select(settings, return_label, **kwargs):
        selected_initial_actions.append(kwargs["initial_action"])
        return next(actions)

    monkeypatch.setattr(about, "select_about_action", fake_select)
    action = about.run_about_menu(
        console,
        UXSettings(),
        return_label="Return to ShellPa",
        opener=lambda url: opened.append(url) or True,
        input_stream=object(),
        output_stream=DummyOutput(),
    )

    assert action is about.AboutAction.RETURN
    assert opened == [about.SHELLPA_REPOSITORY_URL]
    assert selected_initial_actions == [
        about.AboutAction.AMR_PROFILE,
        about.AboutAction.REPOSITORY,
    ]
    assert "Opened in your browser" in output.getvalue()


def test_about_menu_recovers_when_browser_rejects_request(
    monkeypatch,
) -> None:
    actions = iter([about.AboutAction.AMR_PROFILE, about.AboutAction.RETURN])
    monkeypatch.setattr(
        about,
        "select_about_action",
        lambda *args, **kwargs: next(actions),
    )
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    action = about.run_about_menu(
        console,
        UXSettings(),
        return_label="Return",
        opener=lambda url: False,
        input_stream=object(),
        output_stream=DummyOutput(),
    )

    assert action is about.AboutAction.RETURN
    assert "Open this URL manually" in output.getvalue()


def test_nonterminal_about_prints_links_without_opening_browser() -> None:
    opened = []
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)

    action = about.run_about_menu(
        console,
        UXSettings(),
        return_label="Return",
        opener=opened.append,
    )

    rendered = output.getvalue()
    assert action is None
    assert opened == []
    assert about.AMR_GITHUB_URL in rendered
    assert about.KHADIGA_GITHUB_URL in rendered
    assert about.SHELLPA_REPOSITORY_URL in rendered
