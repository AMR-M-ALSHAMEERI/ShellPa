import os
from os import terminal_size
from unittest.mock import Mock

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import shellpa.repl as repl
from shellpa.models import (
    GitContext,
    PermissionMode,
    ProjectType,
    WorkspaceBoundarySource,
    WorkspaceContext,
)
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


def test_update_slash_command_uses_guided_update(monkeypatch) -> None:
    guided_update = Mock()
    monkeypatch.setattr(repl, "display_guided_update", guided_update)
    shell_state = state()
    console = Console()

    assert repl.handle_slash_command("/update", shell_state, console) is True
    guided_update.assert_called_once_with(console)


def test_update_slash_command_saves_notification_preference(monkeypatch) -> None:
    save_settings = Mock()
    monkeypatch.setattr(repl, "save_ux_settings", save_settings)
    shell_state = state()

    assert repl.handle_slash_command("/update weekly", shell_state, Console()) is True
    assert shell_state.settings.update_notifications == "weekly"
    save_settings.assert_called_once_with(shell_state.settings)


def test_codex_login_and_logout_slash_commands(monkeypatch) -> None:
    calls: list[tuple[str, bool | None]] = []
    monkeypatch.setattr(
        repl,
        "login_codex_interactively",
        lambda console, device_code=False: calls.append(("login", device_code)),
    )
    monkeypatch.setattr(
        repl,
        "logout_codex_interactively",
        lambda console: calls.append(("logout", None)),
    )

    assert repl.handle_slash_command(
        "/login device-code",
        state(),
        Console(),
    )
    assert repl.handle_slash_command("/logout", state(), Console())
    assert calls == [("login", True), ("logout", None)]


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


def test_context_slash_command_refreshes_and_displays_workspace(
    monkeypatch,
) -> None:
    runtime = state()
    refreshed = WorkspaceContext(
        root=".",
        current_directory=".",
        boundary_source=WorkspaceBoundarySource.CURRENT_DIRECTORY,
    )
    displayed = []
    monkeypatch.setattr(repl, "detect_workspace", lambda: refreshed)
    monkeypatch.setattr(
        repl,
        "display_workspace_context",
        lambda console, context: displayed.append(context),
    )

    assert repl.handle_slash_command("/context", runtime, Console()) is True
    assert runtime.workspace is refreshed
    assert displayed == [refreshed]


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

    rendered = str(footer())

    assert "ASK" in rendered
    assert "powershell" in rendered
    assert "old-model" not in rendered
    assert "main*" not in rendered


def test_footer_uses_bounded_workspace_identity(
    monkeypatch,
) -> None:
    runtime = state()
    runtime.workspace = WorkspaceContext(
        root=".",
        current_directory=".",
        boundary_source=WorkspaceBoundarySource.GIT,
        project_types=[ProjectType.PYTHON],
        git=GitContext(
            is_repository=True,
            branch="main",
            has_tracked_changes=True,
            tracked_change_count=2,
        ),
    )
    footer = repl.StatusFooter(runtime)
    monkeypatch.setattr(
        repl.shutil,
        "get_terminal_size",
        lambda fallback: terminal_size((90, 24)),
    )

    rendered = str(footer())

    assert "Python" in rendered
    assert "Git main* (2)" in rendered


def test_theme_selector_content_changes_palette_with_selection() -> None:
    signature = repl._theme_selector_content([0])
    ocean = repl._theme_selector_content([1])

    assert "ShellPa Signature" in "".join(text for _, text in signature)
    assert "Ocean / Aurora" in "".join(text for _, text in ocean)
    assert signature[0][0] != ocean[0][0]


def test_theme_selector_keeps_saved_marker_when_preview_moves(monkeypatch) -> None:
    monkeypatch.setattr(repl, "unicode_icons_supported", lambda: True)

    rendered = "".join(text for _, text in repl._theme_selector_content([1], "shellpa"))

    assert "● ShellPa Signature" in rendered
    assert "› ○ Ocean / Aurora" in rendered


def test_live_theme_selector_applies_arrow_key_selection() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        selected = repl.select_theme_interactively(
            "shellpa",
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert selected == "ocean"


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

    assert idle_text.startswith("> ")
    assert typing_text.startswith(">_")


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
