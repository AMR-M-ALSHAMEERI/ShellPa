from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

import shellpa.codex_provider as codex_provider
from shellpa.models import CommandProposal


class FakeTurn:
    def __init__(
        self, final_response: str | None = None, error: Exception | None = None
    ):
        self.final_response = final_response
        self.error = error
        self.interrupted = False

    def run(self):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(final_response=self.final_response)

    def interrupt(self):
        self.interrupted = True


class FakeThread:
    def __init__(self, turn: FakeTurn):
        self.fake_turn = turn
        self.turn_kwargs: dict = {}
        self.user_prompt = ""

    def turn(self, user_prompt, **kwargs):
        self.user_prompt = user_prompt
        self.turn_kwargs = kwargs
        return self.fake_turn


class FakeCodex:
    def __init__(
        self,
        thread: FakeThread,
        *,
        account_type: str | None = "chatgpt",
        plan_type: str | None = "plus",
    ):
        self.thread = thread
        self.account_type = account_type
        self.plan_type = plan_type
        self.thread_kwargs: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def account(self, *, refresh_token=False):
        if self.account_type is None:
            return SimpleNamespace(account=None, requires_openai_auth=True)
        root = SimpleNamespace(type=self.account_type, plan_type=self.plan_type)
        return SimpleNamespace(
            account=SimpleNamespace(root=root),
            requires_openai_auth=True,
        )

    def thread_start(self, **kwargs):
        self.thread_kwargs = kwargs
        return self.thread


def fake_sdk(codex: FakeCodex):
    configs: list[dict] = []

    def config(**kwargs):
        configs.append(kwargs)
        return kwargs

    return SimpleNamespace(
        CodexConfig=config,
        Codex=lambda config: codex,
        ApprovalMode=SimpleNamespace(deny_all="deny_all"),
        Sandbox=SimpleNamespace(read_only="read_only"),
        configs=configs,
    )


def test_codex_provider_returns_structured_proposal_in_isolated_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn = FakeTurn(
        '{"command":"Get-ChildItem","explanation":"List the current directory."}'
    )
    thread = FakeThread(turn)
    codex = FakeCodex(thread)
    sdk = fake_sdk(codex)
    monkeypatch.setattr(codex_provider, "_load_sdk", lambda: sdk)
    monkeypatch.setenv("SHELLPA_MODEL", "codex/default")

    proposal = codex_provider.request_codex_command(
        "Target Operating System: Windows\nTarget Shell: powershell",
        "list files",
    )

    assert proposal == CommandProposal(
        command="Get-ChildItem",
        explanation="List the current directory.",
    )
    assert thread.user_prompt == "list files"
    assert codex.thread_kwargs["ephemeral"] is True
    assert codex.thread_kwargs["approval_mode"] == "deny_all"
    assert codex.thread_kwargs["sandbox"] == "read_only"
    assert codex.thread_kwargs["model"] is None
    assert "Do not call tools" in codex.thread_kwargs["developer_instructions"]
    assert codex.thread_kwargs["cwd"] != str(codex_provider.os.getcwd())
    assert thread.turn_kwargs["output_schema"] == codex_provider.COMMAND_OUTPUT_SCHEMA
    assert thread.turn_kwargs["approval_mode"] == "deny_all"
    assert thread.turn_kwargs["sandbox"] == "read_only"
    assert "mcp_servers={}" in sdk.configs[0]["config_overrides"]


def test_codex_provider_requires_chatgpt_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = FakeCodex(FakeThread(FakeTurn()), account_type=None)
    monkeypatch.setattr(codex_provider, "_load_sdk", lambda: fake_sdk(codex))

    with pytest.raises(codex_provider.CodexAuthenticationError, match="shellpa login"):
        codex_provider.request_codex_command("system", "request")


def test_codex_provider_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = FakeCodex(FakeThread(FakeTurn('{"command":"missing explanation"}')))
    monkeypatch.setattr(codex_provider, "_load_sdk", lambda: fake_sdk(codex))

    with pytest.raises(codex_provider.CodexGenerationError, match="malformed"):
        codex_provider.request_codex_command("system", "request")


def test_codex_provider_wraps_sdk_failure_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = FakeCodex(
        FakeThread(FakeTurn(error=RuntimeError("private provider detail")))
    )
    monkeypatch.setattr(codex_provider, "_load_sdk", lambda: fake_sdk(codex))

    with pytest.raises(codex_provider.CodexGenerationError) as exc_info:
        codex_provider.request_codex_command("system", "request")

    assert "RuntimeError" in str(exc_info.value)
    assert "private provider detail" not in str(exc_info.value)


def test_turn_timeout_interrupts_codex() -> None:
    released = threading.Event()
    interrupted = threading.Event()

    def wait_forever():
        released.wait(timeout=1)

    def interrupt():
        interrupted.set()
        released.set()

    with pytest.raises(codex_provider.CodexGenerationError, match="exceeded"):
        codex_provider._run_turn_with_timeout(wait_forever, interrupt, 0.01)

    assert interrupted.wait(timeout=0.5)


def test_account_status_never_exposes_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = FakeCodex(FakeThread(FakeTurn()), plan_type="pro")
    monkeypatch.setattr(codex_provider, "_load_sdk", lambda: fake_sdk(codex))

    status = codex_provider.inspect_codex_account()

    assert status.authenticated is True
    assert status.plan_type == "pro"
    assert "email" not in status.detail.lower()


def test_missing_sdk_has_actionable_install_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_provider, "codex_sdk_installed", lambda: False)

    status = codex_provider.inspect_codex_account()

    assert status.state is codex_provider.CodexAccountState.UNAVAILABLE
    assert "shellpa[codex]" in status.detail


def test_non_chatgpt_auth_is_not_accepted_as_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = FakeCodex(FakeThread(FakeTurn()), account_type="apiKey")
    monkeypatch.setattr(codex_provider, "_load_sdk", lambda: fake_sdk(codex))

    status = codex_provider.inspect_codex_account()

    assert status.state is codex_provider.CodexAccountState.OTHER
    assert status.authenticated is False
