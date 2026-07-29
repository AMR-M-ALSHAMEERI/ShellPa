from pathlib import Path

import pytest

import shellpa.config as config


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("openrouter/openai/gpt-4o-mini", "openrouter"),
        ("gpt-4o", "openai"),
        ("openai/gpt-4o", "openai"),
        ("gemini/gemini-1.5-pro", "gemini"),
        ("claude-3-haiku-20240307", "anthropic"),
        ("anthropic/claude-3", "anthropic"),
        ("codex/default", "codex"),
        ("ollama/mistral", None),
    ],
)
def test_infer_provider_from_model(model_name: str, expected: str | None) -> None:
    assert config.infer_provider(model_name) == expected


def test_explicit_supported_provider_takes_precedence() -> None:
    assert config.infer_provider("custom/model", " Gemini ") == "gemini"


def test_inspect_config_requires_selected_provider_key() -> None:
    status = config.inspect_config(
        {
            "SHELLPA_MODEL": "openrouter/openai/gpt-4o-mini",
            "OPENAI_API_KEY": "wrong-provider-key",
        }
    )

    assert status.provider == "openrouter"
    assert status.api_key_name == "OPENROUTER_API_KEY"
    assert status.api_key_configured is False
    assert status.is_configured is False


def test_inspect_config_rejects_blank_key() -> None:
    status = config.inspect_config(
        {
            "SHELLPA_MODEL": "gpt-4o",
            "OPENAI_API_KEY": "   ",
        }
    )

    assert status.api_key_configured is False


def test_inspect_config_accepts_nonempty_matching_key() -> None:
    status = config.inspect_config(
        {
            "SHELLPA_MODEL": "gemini/gemini-1.5-pro",
            "GEMINI_API_KEY": "configured",
        }
    )

    assert status.provider == "gemini"
    assert status.is_configured is True


def test_codex_configuration_never_requires_an_api_key() -> None:
    status = config.inspect_config(
        {
            "SHELLPA_MODEL": "codex/default",
            "SHELLPA_PROVIDER": "codex",
        }
    )

    assert status.provider == "codex"
    assert status.api_key_name is None
    assert status.api_key_configured is False
    assert status.is_configured is True


def test_custom_model_keeps_backward_compatible_key_detection() -> None:
    status = config.inspect_config(
        {
            "SHELLPA_MODEL": "custom/provider-model",
            "ANTHROPIC_API_KEY": "configured",
        }
    )

    assert status.provider is None
    assert status.is_configured is True


def test_load_config_returns_status_without_wizard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config, "get_env_path", lambda: Path("missing.env"))
    monkeypatch.setenv("SHELLPA_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "configured")

    status = config.load_config()

    assert status.provider == "openrouter"
    assert status.is_configured is True


def test_load_config_rejects_cancelled_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config, "get_env_path", lambda: Path("missing.env"))
    monkeypatch.setattr(config, "run_setup_wizard", lambda: False)
    for key in (
        "SHELLPA_MODEL",
        "SHELLPA_PROVIDER",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        config.load_config()

    assert exc_info.value.code == 1
