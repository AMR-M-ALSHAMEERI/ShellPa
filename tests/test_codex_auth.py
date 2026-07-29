from types import SimpleNamespace

from rich.console import Console

import shellpa.codex_auth as codex_auth
from shellpa.codex_provider import CodexAccountState, CodexAccountStatus


class FakeLogin:
    login_id = "login-id"
    auth_url = "https://chatgpt.com/auth"
    verification_url = "https://auth.openai.com/codex/device"
    user_code = "ABCD-1234"

    def __init__(self, success: bool = True):
        self.success = success
        self.cancelled = False

    def wait(self):
        return SimpleNamespace(success=self.success, error=None)

    def cancel(self):
        self.cancelled = True


class CancelledLogin(FakeLogin):
    def wait(self):
        raise KeyboardInterrupt


class FakeCodex:
    def __init__(self, login: FakeLogin):
        self.login = login
        self.logged_out = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def login_chatgpt(self):
        return self.login

    def login_chatgpt_device_code(self):
        return self.login

    def logout(self):
        self.logged_out = True


def fake_sdk(codex: FakeCodex):
    return SimpleNamespace(Codex=lambda config: codex)


def test_browser_login_opens_only_official_sdk_url(monkeypatch, tmp_path) -> None:
    login = FakeLogin()
    codex = FakeCodex(login)
    opened: list[str] = []
    monkeypatch.setattr(codex_auth, "_load_sdk", lambda: fake_sdk(codex))
    monkeypatch.setattr(codex_auth, "_client_config", lambda sdk, cwd: {})
    output_path = tmp_path / "output.txt"
    with output_path.open("w", encoding="utf-8") as stream:
        assert codex_auth.login_codex(
            Console(file=stream),
            opener=opened.append,
        )

    assert opened == [login.auth_url]
    rendered = output_path.read_text(encoding="utf-8")
    normalized = " ".join(rendered.split())
    assert (
        "Your ChatGPT account is ready to use with ShellPa through Codex. "
        "Your sign-in session is managed by Codex, not ShellPa."
    ) in normalized


def test_device_code_login_does_not_open_browser(monkeypatch, tmp_path) -> None:
    login = FakeLogin()
    codex = FakeCodex(login)
    opened: list[str] = []
    monkeypatch.setattr(codex_auth, "_load_sdk", lambda: fake_sdk(codex))
    monkeypatch.setattr(codex_auth, "_client_config", lambda sdk, cwd: {})
    output_path = tmp_path / "output.txt"
    with output_path.open("w", encoding="utf-8") as stream:
        console = Console(file=stream)
        assert (
            codex_auth.login_codex(
                console,
                device_code=True,
                opener=opened.append,
            )
            is True
        )

    assert opened == []
    rendered = output_path.read_text(encoding="utf-8")
    assert login.verification_url in rendered
    assert login.user_code in rendered


def test_interrupted_login_is_cancelled_in_codex(monkeypatch, tmp_path) -> None:
    login = CancelledLogin()
    codex = FakeCodex(login)
    monkeypatch.setattr(codex_auth, "_load_sdk", lambda: fake_sdk(codex))
    monkeypatch.setattr(codex_auth, "_client_config", lambda sdk, cwd: {})
    output_path = tmp_path / "output.txt"
    with output_path.open("w", encoding="utf-8") as stream:
        assert codex_auth.login_codex(Console(file=stream)) is False

    assert login.cancelled is True


def test_logout_is_delegated_to_codex(monkeypatch, tmp_path) -> None:
    codex = FakeCodex(FakeLogin())
    monkeypatch.setattr(codex_auth, "_load_sdk", lambda: fake_sdk(codex))
    monkeypatch.setattr(codex_auth, "_client_config", lambda sdk, cwd: {})
    output_path = tmp_path / "output.txt"
    with output_path.open("w", encoding="utf-8") as stream:
        assert codex_auth.logout_codex(Console(file=stream)) is True

    assert codex.logged_out is True


def test_existing_login_defaults_to_keeping_current_session(
    monkeypatch,
    tmp_path,
) -> None:
    output_path = tmp_path / "output.txt"
    monkeypatch.setattr(codex_auth, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(codex_auth, "_select", lambda prompt, choices: "keep")
    monkeypatch.setattr(
        codex_auth,
        "login_codex",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("existing session was replaced")
        ),
    )
    status = CodexAccountStatus(CodexAccountState.CHATGPT, plan_type="plus")

    with output_path.open("w", encoding="utf-8") as stream:
        assert codex_auth.login_codex_interactively(
            Console(file=stream),
            account_status=status,
        )

    rendered = " ".join(output_path.read_text(encoding="utf-8").split())
    assert "already connected through Codex — plus" in rendered
    assert "current Codex session was kept" in rendered


def test_existing_login_can_be_replaced_with_requested_method(
    monkeypatch,
) -> None:
    login_modes: list[bool] = []
    monkeypatch.setattr(codex_auth, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(codex_auth, "_select", lambda prompt, choices: "switch")
    monkeypatch.setattr(
        codex_auth,
        "login_codex",
        lambda console, *, device_code=False: login_modes.append(device_code) or True,
    )
    status = CodexAccountStatus(CodexAccountState.CHATGPT)

    assert codex_auth.login_codex_interactively(
        Console(),
        device_code=True,
        account_status=status,
    )
    assert login_modes == [True]


def test_setup_login_choice_can_select_device_code(monkeypatch) -> None:
    login_modes: list[bool] = []
    monkeypatch.setattr(codex_auth, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(codex_auth, "_select", lambda prompt, choices: "device")
    monkeypatch.setattr(
        codex_auth,
        "login_codex",
        lambda console, *, device_code=False: login_modes.append(device_code) or True,
    )
    status = CodexAccountStatus(CodexAccountState.SIGNED_OUT)

    assert codex_auth.login_codex_interactively(
        Console(),
        device_code=None,
        account_status=status,
    )
    assert login_modes == [True]


def test_logout_defaults_to_keeping_connected_session(monkeypatch) -> None:
    monkeypatch.setattr(codex_auth, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(codex_auth, "_select", lambda prompt, choices: "keep")
    monkeypatch.setattr(
        codex_auth,
        "logout_codex",
        lambda console: (_ for _ in ()).throw(AssertionError("session was signed out")),
    )
    status = CodexAccountStatus(CodexAccountState.CHATGPT)

    assert codex_auth.logout_codex_interactively(
        Console(),
        account_status=status,
    )


def test_logout_requires_explicit_sign_out_choice(monkeypatch) -> None:
    logout_calls: list[bool] = []
    monkeypatch.setattr(codex_auth, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(codex_auth, "_select", lambda prompt, choices: "logout")
    monkeypatch.setattr(
        codex_auth,
        "logout_codex",
        lambda console: logout_calls.append(True) or True,
    )
    status = CodexAccountStatus(CodexAccountState.CHATGPT)

    assert codex_auth.logout_codex_interactively(
        Console(),
        account_status=status,
    )
    assert logout_calls == [True]


def test_logout_reports_already_signed_out_without_prompt(monkeypatch) -> None:
    monkeypatch.setattr(
        codex_auth,
        "_select",
        lambda prompt, choices: (_ for _ in ()).throw(
            AssertionError("signed-out account prompted")
        ),
    )
    status = CodexAccountStatus(CodexAccountState.SIGNED_OUT)

    assert codex_auth.logout_codex_interactively(
        Console(),
        account_status=status,
    )


def test_logout_refuses_noninteractive_session_clear(monkeypatch) -> None:
    monkeypatch.setattr(codex_auth, "_interactive_terminal", lambda: False)
    monkeypatch.setattr(
        codex_auth,
        "logout_codex",
        lambda console: (_ for _ in ()).throw(
            AssertionError("non-interactive session was cleared")
        ),
    )
    status = CodexAccountStatus(CodexAccountState.CHATGPT)

    assert (
        codex_auth.logout_codex_interactively(
            Console(),
            account_status=status,
        )
        is False
    )
