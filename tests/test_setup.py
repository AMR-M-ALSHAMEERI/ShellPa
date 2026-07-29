from pathlib import Path

import pytest
from dotenv import dotenv_values

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

    assert setup.run_setup_wizard() is True

    saved = dotenv_values(env_path)
    assert saved["SHELLPA_PROVIDER"] == "codex"
    assert saved["SHELLPA_MODEL"] == "codex/default"
    assert not any(key.endswith("_API_KEY") for key in saved)
