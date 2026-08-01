from pathlib import Path

import pytest

import shellpa.config as config
import shellpa.credentials as credentials


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
    assert status.credential_source == "environment"


def test_inspect_config_accepts_secret_free_keyring_marker() -> None:
    status = config.inspect_config(
        {
            "SHELLPA_MODEL": "gpt-4o",
            "SHELLPA_PROVIDER": "openai",
            "SHELLPA_CREDENTIAL_STORE": "keyring",
        }
    )

    assert status.is_configured is True
    assert status.credential_source == "keyring"


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
    monkeypatch.setattr(config, "load_environment_sources", lambda: None)
    monkeypatch.delenv("SHELLPA_PROVIDER", raising=False)
    monkeypatch.delenv("SHELLPA_CREDENTIAL_STORE", raising=False)
    monkeypatch.setenv("SHELLPA_MODEL", "openrouter/openai/gpt-4o-mini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "configured")

    status = config.load_config()

    assert status.provider == "openrouter"
    assert status.is_configured is True


def test_load_config_rejects_cancelled_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "load_environment_sources", lambda: None)
    monkeypatch.setattr(
        config,
        "run_setup_wizard",
        lambda: config.SetupOutcome.CANCELLED,
    )
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


def test_project_env_key_is_kept_in_memory_not_process_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_env = tmp_path / ".env"
    local_env.write_text(
        "SHELLPA_PROVIDER=openai\n"
        "SHELLPA_MODEL=gpt-4o\n"
        "OPENAI_API_KEY=project-secret\n",
        encoding="utf-8",
    )
    credentials._SESSION_CREDENTIALS.clear()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SHELLPA_PROVIDER", raising=False)
    monkeypatch.delenv("SHELLPA_MODEL", raising=False)
    monkeypatch.setattr(config, "find_dotenv", lambda **kwargs: str(local_env))
    monkeypatch.setattr(config, "get_env_path", lambda: tmp_path / "missing.env")

    config.load_environment_sources()

    status = config.inspect_config()
    assert status.is_configured is True
    assert status.credential_source == "session"
    assert "OPENAI_API_KEY" not in config.os.environ
    assert (
        credentials.resolve_provider_credential(
            "openai",
            source="session",
            environ={},
        )
        == "project-secret"
    )
    credentials._SESSION_CREDENTIALS.clear()
