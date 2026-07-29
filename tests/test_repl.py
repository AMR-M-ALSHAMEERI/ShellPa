import os
from os import terminal_size

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import shellpa.repl as repl
from shellpa.models import PermissionMode
from shellpa.ux import UXSettings


def state() -> repl.InteractiveState:
    return repl.InteractiveState(
        mode=PermissionMode.ASK,
        model_name="old-model",
        env_info={"os": "Windows", "shell": "powershell"},
        settings=UXSettings(),
    )


def test_non_slash_input_is_not_consumed() -> None:
    assert repl.handle_slash_command("list files", state(), Console()) is False


def test_mode_command_changes_runtime_mode() -> None:
    runtime = state()
    assert repl.handle_slash_command("/mode trusted", runtime, Console()) is True
    assert runtime.mode is PermissionMode.TRUSTED


def test_model_command_changes_only_active_session(
    monkeypatch,
) -> None:
    runtime = state()
    monkeypatch.delenv("SHELLPA_MODEL", raising=False)

    repl.handle_slash_command("/model new/model", runtime, Console())

    assert runtime.model_name == "new/model"
    assert os.environ["SHELLPA_MODEL"] == "new/model"


def test_theme_and_motion_commands_persist_visual_settings(
    monkeypatch,
) -> None:
    runtime = state()
    saved = []
    monkeypatch.setattr(
        repl, "save_ux_settings", lambda settings: saved.append(settings)
    )

    repl.handle_slash_command("/theme minimal", runtime, Console())
    repl.handle_slash_command("/motion off", runtime, Console())

    assert runtime.settings.theme == "minimal"
    assert runtime.settings.animation == "off"
    assert runtime.settings.reduced_motion is True
    assert len(saved) == 2


def test_theme_command_opens_live_selector_when_no_argument(
    monkeypatch,
) -> None:
    runtime = state()
    saved = []
    monkeypatch.setattr(repl, "_has_interactive_terminal", lambda: True)
    monkeypatch.setattr(
        repl,
        "select_theme_interactively",
        lambda current: "aurora",
    )
    monkeypatch.setattr(
        repl, "save_ux_settings", lambda settings: saved.append(settings)
    )

    repl.handle_slash_command("/theme", runtime, Console())

    assert runtime.settings.theme == "aurora"
    assert len(saved) == 1


def test_mode_and_motion_open_interactive_selectors_without_arguments(
    monkeypatch,
) -> None:
    runtime = state()
    monkeypatch.setattr(repl, "_has_interactive_terminal", lambda: True)
    monkeypatch.setattr(repl, "_select_mode", lambda current: PermissionMode.PLAN)
    monkeypatch.setattr(repl, "_select_motion", lambda current: "compact")
    monkeypatch.setattr(repl, "save_ux_settings", lambda settings: None)

    repl.handle_slash_command("/mode", runtime, Console())
    repl.handle_slash_command("/motion", runtime, Console())

    assert runtime.mode is PermissionMode.PLAN
    assert runtime.settings.animation == "compact"
    assert runtime.settings.reduced_motion is True


def test_modes_have_distinct_stable_icons_and_descriptions(
    monkeypatch,
) -> None:
    monkeypatch.setattr(repl, "unicode_icons_supported", lambda: True)

    icons = {repl.mode_icon(mode) for mode in repl.MODE_ORDER}
    descriptions = {
        repl.MODE_PRESENTATIONS[mode].description for mode in repl.MODE_ORDER
    }

    assert icons == {"?", "◇", "✓"}
    assert len(descriptions) == 3


def test_live_mode_selector_applies_down_arrow_selection() -> None:
    runtime = state()
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        selected = repl.select_mode_interactively(
            runtime,
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert selected is PermissionMode.PLAN


def test_live_motion_selector_applies_down_arrow_selection() -> None:
    runtime = state()
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        selected = repl.select_motion_interactively(
            runtime,
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert selected == "compact"


def test_exit_command_sets_exit_state() -> None:
    runtime = state()
    repl.handle_slash_command("/exit", runtime, Console())
    assert runtime.should_exit is True


def test_about_slash_command_uses_shared_about_renderer(
    monkeypatch,
) -> None:
    runtime = state()
    calls = []
    monkeypatch.setattr(
        repl,
        "run_about_menu",
        lambda console, settings, **kwargs: calls.append(
            (settings, kwargs["return_label"])
        ),
    )

    assert repl.handle_slash_command("/about", runtime, Console()) is True
    assert calls == [(runtime.settings, "Return to ShellPa")]


def test_history_is_session_local() -> None:
    first = state()
    second = state()
    first.requests.append("private request")
    assert second.requests == []


def test_footer_collapses_model_and_full_path_in_narrow_terminal(
    monkeypatch,
) -> None:
    runtime = state()
    footer = repl.StatusFooter(runtime)
    monkeypatch.setattr(
        repl.shutil, "get_terminal_size", lambda fallback: terminal_size((50, 24))
    )
    monkeypatch.setattr(footer, "_git_status", lambda: "main*")

    rendered = str(footer())

    assert "ASK" in rendered
    assert "powershell" in rendered
    assert "old-model" not in rendered
    assert "main*" not in rendered


def test_theme_selector_content_changes_palette_with_selection() -> None:
    ocean = repl._theme_selector_content([0])
    aurora = repl._theme_selector_content([1])

    assert "Ocean / Aurora" in "".join(text for _, text in ocean)
    assert "Aurora Violet" in "".join(text for _, text in aurora)
    assert ocean[0][0] != aurora[0][0]


def test_live_theme_selector_applies_arrow_key_selection() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        selected = repl.select_theme_interactively(
            "ocean",
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert selected == "aurora"


def test_idle_prompt_animates_only_while_input_is_empty(monkeypatch) -> None:
    class Buffer:
        text = ""

    class App:
        current_buffer = Buffer()

    app = App()
    monkeypatch.setattr(repl, "get_app", lambda: app)
    monkeypatch.setattr(repl, "unicode_icons_supported", lambda: True)
    monkeypatch.setattr(repl.time, "monotonic", lambda: 0.25)
    renderer = repl._idle_prompt(UXSettings(animation="full"))

    idle_text = "".join(text for _, text in renderer())
    app.current_buffer.text = "typing"
    typing_text = "".join(text for _, text in renderer())

    assert idle_text.startswith("✧")
    assert typing_text.startswith("✦")


def test_interactive_session_accepts_legacy_exit_word(
    monkeypatch,
) -> None:
    runtime = state()

    class FakeSession:
        def __init__(self, **kwargs):
            pass

        def prompt(self, *args, **kwargs):
            return "exit"

    monkeypatch.setattr(repl, "PromptSession", FakeSession)
    monkeypatch.setattr(repl, "_has_interactive_terminal", lambda: True)
    repl.run_interactive_session(
        Console(),
        runtime,
        lambda query, mode: (_ for _ in ()).throw(AssertionError("should not process")),
    )

    assert runtime.should_exit is True


def test_redirected_session_does_not_initialize_prompt_toolkit(
    monkeypatch,
) -> None:
    runtime = state()
    monkeypatch.setattr(repl, "_has_interactive_terminal", lambda: False)
    monkeypatch.setattr(repl.sys, "stdin", iter(["/exit\n"]))
    monkeypatch.setattr(
        repl,
        "PromptSession",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("prompt toolkit should not initialize")
        ),
    )

    repl.run_interactive_session(Console(), runtime, lambda query, mode: None)

    assert runtime.should_exit is True
