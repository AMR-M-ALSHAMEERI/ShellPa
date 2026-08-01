from pathlib import Path

import pytest
from dotenv import dotenv_values
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

import shellpa.codex_auth as codex_auth
import shellpa.credentials as credentials
import shellpa.setup as setup
from shellpa.selector import SelectorAction, SelectorResult
from shellpa.ux import UXSettings


class Answer:
    def __init__(self, value: str):
        self.value = value

    def ask(self) -> str:
        return self.value


class BackendStatus:
    available = True
    name = "Test Credential Store"
    detail = "Secure test storage is available."


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def status(self) -> BackendStatus:
        return BackendStatus()

    def set(self, provider: str, value: str) -> None:
        self.values[provider] = value.strip()

    def get(self, provider: str) -> str:
        return self.values[provider]

    def delete(self, provider: str) -> None:
        self.values.pop(provider, None)


class UnavailableStatus:
    available = False
    name = "Unavailable"
    detail = "No secure credential store is available."


class UnavailableCredentialStore(FakeCredentialStore):
    def status(self) -> UnavailableStatus:
        return UnavailableStatus()


class FailingCredentialStore(FakeCredentialStore):
    def set(self, provider: str, value: str) -> None:
        raise setup.CredentialStoreError("controlled storage failure")


@pytest.fixture(autouse=True)
def clear_session_credentials() -> None:
    credentials._SESSION_CREDENTIALS.clear()


def test_native_provider_model_and_recovery_navigation() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        provider = setup.select_provider_interactively(
            "openrouter",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert provider.action is SelectorAction.SELECT
    assert provider.value == "openai"

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\x1b[B\x1b[B\rcustom/model\r")
        model = setup.select_model_interactively(
            "openai",
            "gpt-4o",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert model.action is SelectorAction.SELECT
    assert model.value == "custom/model"

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        recovery = setup.select_recovery_interactively(
            "openai",
            "ask",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert recovery.action is SelectorAction.SELECT
    assert recovery.value == "allow"


def test_native_model_escape_returns_back() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b")
        result = setup.select_model_interactively(
            "openai",
            "gpt-4o",
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )

    assert result.action is SelectorAction.BACK


def test_native_cancel_confirmation_keeps_safe_default() -> None:
    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\r")
        keep_configuring = setup.confirm_setup_cancel_interactively(
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert keep_configuring is False

    with create_pipe_input() as pipe_input:
        pipe_input.send_text("\x1b[B\r")
        cancel_setup = setup.confirm_setup_cancel_interactively(
            UXSettings(),
            input_stream=pipe_input,
            output_stream=DummyOutput(),
        )
    assert cancel_setup is True


def test_setup_persists_provider_and_reprompts_for_blank_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["openai", "gpt-4o"])
    passwords = iter(["   ", "test-key"])
    env_path = tmp_path / ".shellpa.env"
    store = FakeCredentialStore()
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
    assert setup.run_setup_wizard(store) is setup.SetupOutcome.SAVED

    saved = dotenv_values(env_path)
    assert saved["SHELLPA_PROVIDER"] == "openai"
    assert saved["SHELLPA_MODEL"] == "gpt-4o"
    assert saved["SHELLPA_CREDENTIAL_STORE"] == "keyring"
    assert "OPENAI_API_KEY" not in saved
    assert store.values["openai"] == "test-key"
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

    assert setup.run_setup_wizard() is setup.SetupOutcome.SAVED

    saved = dotenv_values(env_path)
    assert saved["SHELLPA_PROVIDER"] == "codex"
    assert saved["SHELLPA_MODEL"] == "codex/default"
    assert not any(key.endswith("_API_KEY") for key in saved)


def test_setup_migrates_legacy_key_only_after_secure_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["openai", "gpt-4o", "migrate"])
    env_path = tmp_path / ".shellpa.env"
    env_path.write_text(
        "SHELLPA_PROVIDER=openai\nSHELLPA_MODEL=gpt-4o\nOPENAI_API_KEY=legacy-secret\n",
        encoding="utf-8",
    )
    store = FakeCredentialStore()
    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer(next(selections)),
    )
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: pytest.fail("migration requested a new key"),
    )
    monkeypatch.setattr(setup, "get_env_path", lambda: env_path)

    assert setup.run_setup_wizard(store) is setup.SetupOutcome.SAVED

    saved = dotenv_values(env_path)
    assert saved["SHELLPA_CREDENTIAL_STORE"] == "keyring"
    assert "OPENAI_API_KEY" not in saved
    assert store.values["openai"] == "legacy-secret"


def test_unavailable_backend_uses_session_without_plaintext_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".shellpa.env"
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: Answer("session-secret"),
    )
    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer("session"),
    )

    plan = setup._configure_api_credential(
        "openai",
        env_path,
        UnavailableCredentialStore(),
    )

    assert isinstance(plan, setup.CredentialPlan)
    assert plan.source == "session"
    assert not env_path.exists()
    assert setup._apply_credential_plan(plan, UnavailableCredentialStore()) == "session"
    assert credentials.has_session_credential("openai")


def test_failed_migration_preserves_legacy_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".shellpa.env"
    env_path.write_text(
        "SHELLPA_PROVIDER=openai\nOPENAI_API_KEY=legacy-secret\n",
        encoding="utf-8",
    )
    selections = iter(["migrate"])
    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer(next(selections)),
    )
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: Answer(None),
    )
    monkeypatch.setattr(
        setup.questionary,
        "confirm",
        lambda *args, **kwargs: Answer(True),
    )

    plan = setup._configure_api_credential(
        "openai",
        env_path,
        FailingCredentialStore(),
    )
    assert isinstance(plan, setup.CredentialPlan)
    assert setup._apply_credential_plan(plan, FailingCredentialStore()) is None
    assert dotenv_values(env_path)["OPENAI_API_KEY"] == "legacy-secret"


def test_codex_setup_can_install_and_start_device_login(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["codex", "codex/default", "install", "ask", "save"])
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

    assert setup.run_setup_wizard() is setup.SetupOutcome.SAVED
    assert installed is True
    assert login_modes == [None]
    assert dotenv_values(env_path)["SHELLPA_PROVIDER"] == "codex"


def test_setup_cancel_discards_credential_and_metadata_draft(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selections = iter(["openai", "gpt-4o", "ask", "cancel"])
    env_path = tmp_path / ".shellpa.env"
    store = FakeCredentialStore()
    monkeypatch.setattr(
        setup.questionary,
        "select",
        lambda *args, **kwargs: Answer(next(selections)),
    )
    monkeypatch.setattr(
        setup.questionary,
        "password",
        lambda *args, **kwargs: Answer("draft-secret"),
    )
    monkeypatch.setattr(setup, "get_env_path", lambda: env_path)
    monkeypatch.setattr(setup, "_interactive_terminal", lambda: True)

    assert setup.run_setup_wizard(store) is setup.SetupOutcome.CANCELLED
    assert store.values == {}
    assert not env_path.exists()
    assert not credentials.has_session_credential("openai")


def test_setup_back_moves_exactly_one_screen_and_saves_only_after_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".shellpa.env"
    store = FakeCredentialStore()
    calls: list[str] = []
    recovery_results = iter(
        [
            SelectorResult(SelectorAction.BACK),
            SelectorResult(SelectorAction.SELECT, "ask"),
            SelectorResult(SelectorAction.SELECT, "allow"),
        ]
    )
    review_results = iter(["back", "save"])

    def choose_provider(*args: object, **kwargs: object) -> SelectorResult[str]:
        calls.append("provider")
        return SelectorResult(SelectorAction.SELECT, "openai")

    def choose_model(*args: object, **kwargs: object) -> SelectorResult[str]:
        calls.append("model")
        return SelectorResult(SelectorAction.SELECT, "gpt-4o")

    def configure_credential(*args: object, **kwargs: object) -> setup.CredentialPlan:
        calls.append("credential")
        return setup.CredentialPlan("openai", "keyring", "draft-secret")

    def choose_recovery(*args: object, **kwargs: object) -> SelectorResult[str]:
        calls.append("recovery")
        return next(recovery_results)

    def review(*args: object, **kwargs: object) -> str:
        calls.append("review")
        return next(review_results)

    monkeypatch.setattr(setup, "get_env_path", lambda: env_path)
    monkeypatch.setattr(setup, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(setup, "_choose_provider", choose_provider)
    monkeypatch.setattr(setup, "_choose_model", choose_model)
    monkeypatch.setattr(setup, "_configure_api_credential", configure_credential)
    monkeypatch.setattr(setup, "_choose_recovery", choose_recovery)
    monkeypatch.setattr(setup, "_review_configuration_draft", review)

    assert setup.run_setup_wizard(store) is setup.SetupOutcome.SAVED
    assert calls == [
        "provider",
        "model",
        "credential",
        "recovery",
        "credential",
        "recovery",
        "review",
        "recovery",
        "review",
    ]
    assert store.values == {"openai": "draft-secret"}
    assert dotenv_values(env_path)["SHELLPA_RECOVERY_PERMISSION_OPENAI"] == "allow"


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
