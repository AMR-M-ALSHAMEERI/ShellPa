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
