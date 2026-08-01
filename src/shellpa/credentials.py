"""Operating-system credential storage for API-backed providers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

import keyring

SERVICE_NAME = "shellpa"
PROVIDER_API_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class CredentialBackendState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class CredentialBackendStatus:
    state: CredentialBackendState
    name: str
    detail: str

    @property
    def available(self) -> bool:
        return self.state is CredentialBackendState.AVAILABLE


class CredentialStoreError(RuntimeError):
    """Base error for secure credential storage failures."""


class CredentialStoreUnavailableError(CredentialStoreError):
    """Raised when the operating system has no usable credential backend."""


class CredentialNotFoundError(CredentialStoreError):
    """Raised when a configured provider credential cannot be retrieved."""


def _friendly_backend_name(backend: Any) -> str:
    identity = f"{type(backend).__module__}.{type(backend).__name__}"
    normalized = identity.lower()
    if "windows" in normalized or "winvault" in normalized:
        return "Windows Credential Locker"
    if "macos" in normalized or "keychain" in normalized:
        return "macOS Keychain"
    if "secretservice" in normalized:
        return "Linux Secret Service"
    if "kwallet" in normalized:
        return "KWallet"
    if "fail" in normalized:
        return "Unavailable"
    return type(backend).__name__


def inspect_credential_backend(
    keyring_module: Any = keyring,
) -> CredentialBackendStatus:
    """Inspect backend capability without retrieving a stored credential."""
    try:
        backend = keyring_module.get_keyring()
        priority = float(getattr(backend, "priority", 0))
        name = _friendly_backend_name(backend)
    except Exception as exc:
        return CredentialBackendStatus(
            CredentialBackendState.ERROR,
            "Unavailable",
            f"Credential backend inspection failed: {type(exc).__name__}.",
        )
    if priority <= 0 or name == "Unavailable":
        return CredentialBackendStatus(
            CredentialBackendState.UNAVAILABLE,
            name,
            "No supported operating-system credential store is available.",
        )
    return CredentialBackendStatus(
        CredentialBackendState.AVAILABLE,
        name,
        f"Secure credentials are managed by {name}.",
    )


class CredentialStore:
    """Small provider-key abstraction over the active system keyring."""

    def __init__(self, keyring_module: Any = keyring) -> None:
        self._keyring = keyring_module

    def status(self) -> CredentialBackendStatus:
        return inspect_credential_backend(self._keyring)

    def _require_backend(self) -> CredentialBackendStatus:
        status = self.status()
        if not status.available:
            raise CredentialStoreUnavailableError(status.detail)
        return status

    def set(self, provider: str, credential: str) -> None:
        self._require_backend()
        value = credential.strip()
        if not value:
            raise CredentialStoreError("Credential cannot be empty.")
        try:
            self._keyring.set_password(SERVICE_NAME, provider, value)
        except Exception as exc:
            raise CredentialStoreError(
                f"Credential storage failed: {type(exc).__name__}."
            ) from exc

    def get(self, provider: str) -> str:
        self._require_backend()
        try:
            value = self._keyring.get_password(SERVICE_NAME, provider)
        except Exception as exc:
            raise CredentialStoreError(
                f"Credential retrieval failed: {type(exc).__name__}."
            ) from exc
        if not isinstance(value, str) or not value.strip():
            raise CredentialNotFoundError(
                f"No secure credential is stored for {provider}."
            )
        return value

    def delete(self, provider: str) -> None:
        self._require_backend()
        try:
            existing = self._keyring.get_password(SERVICE_NAME, provider)
            if not existing:
                return
            self._keyring.delete_password(SERVICE_NAME, provider)
        except Exception as exc:
            raise CredentialStoreError(
                f"Credential removal failed: {type(exc).__name__}."
            ) from exc


_SESSION_CREDENTIALS: dict[str, str] = {}


def set_session_credential(provider: str, credential: str) -> None:
    """Keep one credential in memory for the lifetime of this process."""
    value = credential.strip()
    if not value:
        raise CredentialStoreError("Credential cannot be empty.")
    _SESSION_CREDENTIALS[provider] = value


def clear_session_credential(provider: str) -> None:
    _SESSION_CREDENTIALS.pop(provider, None)


def has_session_credential(provider: str | None) -> bool:
    return bool(provider and _SESSION_CREDENTIALS.get(provider))


def resolve_provider_credential(
    provider: str,
    *,
    source: str | None,
    environ: Mapping[str, str] | None = None,
    store: CredentialStore | None = None,
) -> str:
    """Resolve a provider key without adding it to the process environment."""
    session_value = _SESSION_CREDENTIALS.get(provider)
    if session_value:
        return session_value

    values = os.environ if environ is None else environ
    key_name = PROVIDER_API_KEYS.get(provider)
    environment_value = (values.get(key_name or "") or "").strip()
    if environment_value:
        return environment_value

    if source == "keyring":
        return (store or CredentialStore()).get(provider)
    raise CredentialNotFoundError(f"No credential is configured for {provider}.")
