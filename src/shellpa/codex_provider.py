"""Optional ChatGPT-subscription generation through the official Codex SDK."""

from __future__ import annotations

import importlib.util
import os
import queue
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .models import CommandProposal

CODEX_SDK_REQUIREMENT = "openai-codex==0.144.4"
CODEX_EXTRA_INSTALL = 'python -m pip install "shellpa[codex]"'
DEFAULT_CODEX_TIMEOUT_SECONDS = 90.0
COMMAND_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "minLength": 1},
        "explanation": {"type": "string", "minLength": 1},
    },
    "required": ["command", "explanation"],
    "additionalProperties": False,
}
CODEX_THREAD_CONFIG: dict[str, Any] = {
    "include_apps_instructions": False,
    "include_collaboration_mode_instructions": False,
    "include_environment_context": False,
    "include_permissions_instructions": False,
    "skills": {"include_instructions": False},
    "web_search": "disabled",
    "features": {
        "apps": False,
        "browser_use": False,
        "computer_use": False,
        "multi_agent": False,
        "plugins": False,
        "shell_tool": False,
        "unified_exec": False,
        "web_search": False,
    },
}
CODEX_CONFIG_OVERRIDES = (
    "mcp_servers={}",
    'web_search="disabled"',
    "features.apps=false",
    "features.browser_use=false",
    "features.computer_use=false",
    "features.multi_agent=false",
    "features.plugins=false",
    "features.shell_tool=false",
    "features.unified_exec=false",
    "features.web_search=false",
    "skills.include_instructions=false",
)
CODEX_GENERATION_INSTRUCTIONS = """
You are the command-proposal component inside ShellPa.
Do not call tools, inspect files, execute commands, browse, or modify anything.
Return only the JSON object requested by the supplied schema.
ShellPa performs its own deterministic safety assessment and is the only
component allowed to ask the user for execution authorization.
""".strip()


class CodexProviderError(RuntimeError):
    """Base error for the optional Codex provider."""


class CodexSDKUnavailableError(CodexProviderError):
    """The optional Python SDK is not installed."""


class CodexAuthenticationError(CodexProviderError):
    """Codex is not authenticated with a ChatGPT account."""


class CodexGenerationError(CodexProviderError):
    """Codex could not return a valid command proposal."""


class CodexAccountState(str, Enum):
    UNAVAILABLE = "unavailable"
    SIGNED_OUT = "signed_out"
    CHATGPT = "chatgpt"
    OTHER = "other"
    ERROR = "error"


@dataclass(frozen=True)
class CodexAccountStatus:
    state: CodexAccountState
    plan_type: str | None = None
    detail: str = ""

    @property
    def authenticated(self) -> bool:
        return self.state is CodexAccountState.CHATGPT


def codex_sdk_installed() -> bool:
    """Check for the optional SDK without importing or starting it."""
    return importlib.util.find_spec("openai_codex") is not None


def _load_sdk() -> Any:
    if not codex_sdk_installed():
        raise CodexSDKUnavailableError(
            f"The optional Codex provider is not installed. Run: {CODEX_EXTRA_INSTALL}"
        )
    import openai_codex

    return openai_codex


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _account_details(response: Any) -> tuple[str | None, str | None]:
    account = getattr(response, "account", None)
    if account is None:
        return None, None
    root = getattr(account, "root", account)
    return _enum_value(getattr(root, "type", None)), _enum_value(
        getattr(root, "plan_type", None)
    )


def _client_config(sdk: Any, cwd: str) -> Any:
    return sdk.CodexConfig(
        cwd=cwd,
        config_overrides=CODEX_CONFIG_OVERRIDES,
        client_name="shellpa",
        client_title="ShellPa",
    )


def inspect_codex_account() -> CodexAccountStatus:
    """Read Codex-managed account state without reading credential files."""
    try:
        sdk = _load_sdk()
    except CodexSDKUnavailableError as exc:
        return CodexAccountStatus(
            CodexAccountState.UNAVAILABLE,
            detail=str(exc),
        )

    try:
        with tempfile.TemporaryDirectory(prefix="shellpa-codex-status-") as temp_dir:
            with sdk.Codex(config=_client_config(sdk, temp_dir)) as codex:
                account_type, plan_type = _account_details(
                    codex.account(refresh_token=False)
                )
    except Exception as exc:
        return CodexAccountStatus(
            CodexAccountState.ERROR,
            detail=f"Codex account check failed: {type(exc).__name__}.",
        )

    if account_type == "chatgpt":
        return CodexAccountStatus(
            CodexAccountState.CHATGPT,
            plan_type=plan_type,
            detail="ChatGPT account is connected.",
        )
    if account_type is None:
        return CodexAccountStatus(
            CodexAccountState.SIGNED_OUT,
            detail="No ChatGPT account is connected.",
        )
    return CodexAccountStatus(
        CodexAccountState.OTHER,
        detail=(
            f"Codex is using {account_type} authentication, not a ChatGPT account."
        ),
    )


def _configured_model() -> str | None:
    model = (os.getenv("SHELLPA_MODEL") or "").strip()
    if not model or model == "codex/default":
        return None
    if model.startswith("codex/"):
        return model.removeprefix("codex/") or None
    return model


def _configured_timeout() -> float:
    raw = (os.getenv("SHELLPA_CODEX_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_CODEX_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CODEX_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_CODEX_TIMEOUT_SECONDS


def _run_turn_with_timeout(
    run: Callable[[], Any],
    interrupt: Callable[[], Any],
    timeout_seconds: float,
) -> Any:
    results: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            results.put((True, run()))
        except BaseException as exc:
            results.put((False, exc))

    thread = threading.Thread(
        target=worker,
        name="shellpa-codex-turn",
        daemon=True,
    )
    thread.start()
    try:
        succeeded, value = results.get(timeout=timeout_seconds)
    except queue.Empty as exc:
        try:
            interrupt()
        except Exception:
            pass
        raise CodexGenerationError(
            f"Codex generation exceeded {timeout_seconds:g} seconds."
        ) from exc
    if not succeeded:
        if isinstance(value, BaseException):
            raise value
        raise CodexGenerationError("Codex generation failed unexpectedly.")
    return value


def request_codex_command(
    system_prompt: str,
    user_prompt: str,
) -> CommandProposal:
    """Generate one proposal without granting Codex project or execution access."""
    sdk = _load_sdk()
    timeout_seconds = _configured_timeout()

    try:
        with tempfile.TemporaryDirectory(
            prefix="shellpa-codex-generation-"
        ) as temp_dir:
            with sdk.Codex(config=_client_config(sdk, temp_dir)) as codex:
                account_type, _ = _account_details(codex.account(refresh_token=False))
                if account_type != "chatgpt":
                    raise CodexAuthenticationError(
                        "Codex is not connected to a ChatGPT account. "
                        "Run: shellpa login"
                    )

                thread = codex.thread_start(
                    approval_mode=sdk.ApprovalMode.deny_all,
                    config=CODEX_THREAD_CONFIG,
                    cwd=temp_dir,
                    developer_instructions=(
                        f"{CODEX_GENERATION_INSTRUCTIONS}\n\n{system_prompt}"
                    ),
                    ephemeral=True,
                    model=_configured_model(),
                    sandbox=sdk.Sandbox.read_only,
                )
                turn = thread.turn(
                    user_prompt,
                    approval_mode=sdk.ApprovalMode.deny_all,
                    output_schema=COMMAND_OUTPUT_SCHEMA,
                    sandbox=sdk.Sandbox.read_only,
                )
                result = _run_turn_with_timeout(
                    turn.run,
                    turn.interrupt,
                    timeout_seconds,
                )
    except (CodexProviderError, KeyboardInterrupt):
        raise
    except Exception as exc:
        raise CodexGenerationError(
            f"Codex generation failed: {type(exc).__name__}."
        ) from exc

    final_response = getattr(result, "final_response", None)
    if not isinstance(final_response, str) or not final_response.strip():
        raise CodexGenerationError("Codex returned no final command proposal.")
    try:
        return CommandProposal.model_validate_json(final_response)
    except Exception as exc:
        raise CodexGenerationError(
            "Codex returned a malformed command proposal."
        ) from exc


class CodexSubscriptionProvider:
    """Provider adapter used by ShellPa's neutral generation router."""

    def request_command(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> CommandProposal:
        return request_codex_command(system_prompt, user_prompt)
