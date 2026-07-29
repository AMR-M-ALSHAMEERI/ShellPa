from pathlib import Path

import pytest
from dotenv import dotenv_values

import shellpa.codex_auth as codex_auth
import shellpa.setup as setup


class Answer:
    def __init__(self, value: str):
        self.value = value

    def ask(self) -> str:
        return self.value


def test_setup_persists_provider_and_reprompts_for_blank_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["openai", "gpt-4o"])
    passwords = iter(["   ", "test-key"])
    env_path = tmp_path / ".shellpa.env"
    monkeypatch.setenv("SHELLPA_PROVIDER", "original")
    monkeypatch.setenv("SHELLPA_MODEL", "original")
    monkeypatch.setenv("OPENAI_API_KEY", "original")

    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer(next(selections)),
    )
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: Answer(next(passwords)),
    )
    monkeypatch.setattr(setup, "get_env_path", lambda: env_path)
    assert setup.run_setup_wizard() is True

    saved = dotenv_values(env_path)
    assert saved["SHELLPA_PROVIDER"] == "openai"
    assert saved["SHELLPA_MODEL"] == "gpt-4o"
    assert saved["OPENAI_API_KEY"] == "test-key"
    assert setup.os.environ["SHELLPA_PROVIDER"] == "openai"


def test_setup_persists_codex_without_requesting_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["codex", "codex/default"])
    env_path = tmp_path / ".shellpa.env"
    monkeypatch.setenv("SHELLPA_PROVIDER", "original")
    monkeypatch.setenv("SHELLPA_MODEL", "original")

    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer(next(selections)),
    )
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: pytest.fail("Codex setup requested an API key"),
    )
    monkeypatch.setattr(setup, "get_env_path", lambda: env_path)
    monkeypatch.setattr(setup, "codex_sdk_installed", lambda: True)
    monkeypatch.setattr(setup, "_interactive_terminal", lambda: False)

    assert setup.run_setup_wizard() is True

    saved = dotenv_values(env_path)
    assert saved["SHELLPA_PROVIDER"] == "codex"
    assert saved["SHELLPA_MODEL"] == "codex/default"
    assert not any(key.endswith("_API_KEY") for key in saved)


def test_codex_setup_can_install_and_start_device_login(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["codex", "codex/default", "install"])
    env_path = tmp_path / ".shellpa.env"
    installed = False
    login_modes: list[bool] = []

    def sdk_installed() -> bool:
        return installed

    def install(*args: object, **kwargs: object) -> bool:
        nonlocal installed
        installed = True
        return True

    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer(next(selections)),
    )
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: pytest.fail("Codex setup requested an API key"),
    )
    monkeypatch.setattr(setup, "get_env_path", lambda: env_path)
    monkeypatch.setattr(setup, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(setup, "codex_sdk_installed", sdk_installed)
    monkeypatch.setattr(setup, "install_codex_sdk", install)
    monkeypatch.setattr(
        codex_auth,
        "login_codex_interactively",
        lambda console, *, device_code=False: login_modes.append(device_code) or True,
    )

    assert setup.run_setup_wizard() is True
    assert installed is True
    assert login_modes == [None]
    assert dotenv_values(env_path)["SHELLPA_PROVIDER"] == "codex"


def test_codex_setup_does_not_install_outside_interactive_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup, "codex_sdk_installed", lambda: False)
    monkeypatch.setattr(setup, "_interactive_terminal", lambda: False)
    monkeypatch.setattr(
        setup,
        "install_codex_sdk",
        lambda *args, **kwargs: pytest.fail("non-interactive install attempted"),
    )

    assert setup._prepare_codex_provider() == "later"


def test_codex_setup_can_defer_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup, "codex_sdk_installed", lambda: False)
    monkeypatch.setattr(setup, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer("later"),
    )
    monkeypatch.setattr(
        setup,
        "install_codex_sdk",
        lambda *args, **kwargs: pytest.fail("deferred install attempted"),
    )

    assert setup._prepare_codex_provider() == "later"
