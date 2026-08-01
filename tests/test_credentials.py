from types import SimpleNamespace

import pytest

import shellpa.credentials as credentials


class WindowsBackend:
    priority = 5


class FailBackend:
    priority = 0


class FakeKeyring:
    def __init__(self, backend=None):
        self.backend = backend or WindowsBackend()
        self.values: dict[tuple[str, str], str] = {}

    def get_keyring(self):
        return self.backend

    def set_password(self, service: str, account: str, value: str) -> None:
        self.values[(service, account)] = value

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def delete_password(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


@pytest.fixture(autouse=True)
def clear_session_credentials() -> None:
    credentials._SESSION_CREDENTIALS.clear()


def test_backend_status_is_secret_free_and_friendly() -> None:
    status = credentials.inspect_credential_backend(FakeKeyring())

    assert status.available is True
    assert status.name == "Windows Credential Locker"
    assert "Windows Credential Locker" in status.detail


def test_unavailable_backend_fails_closed() -> None:
    fake = FakeKeyring(FailBackend())
    status = credentials.inspect_credential_backend(fake)

    assert status.state is credentials.CredentialBackendState.UNAVAILABLE
    with pytest.raises(credentials.CredentialStoreUnavailableError):
        credentials.CredentialStore(fake).set("openai", "secret")


def test_store_round_trip_and_delete() -> None:
    fake = FakeKeyring()
    store = credentials.CredentialStore(fake)

    store.set("openai", "  secure-value  ")
    assert store.get("openai") == "secure-value"

    store.delete("openai")
    with pytest.raises(credentials.CredentialNotFoundError):
        store.get("openai")


def test_resolve_prefers_session_then_environment_then_keyring() -> None:
    fake = FakeKeyring()
    store = credentials.CredentialStore(fake)
    store.set("openai", "stored-value")

    assert (
        credentials.resolve_provider_credential(
            "openai",
            source="keyring",
            environ={"OPENAI_API_KEY": "environment-value"},
            store=store,
        )
        == "environment-value"
    )

    credentials.set_session_credential("openai", "session-value")
    assert (
        credentials.resolve_provider_credential(
            "openai",
            source="keyring",
            environ={"OPENAI_API_KEY": "environment-value"},
            store=store,
        )
        == "session-value"
    )


def test_missing_credential_never_returns_a_placeholder() -> None:
    with pytest.raises(credentials.CredentialNotFoundError):
        credentials.resolve_provider_credential(
            "openai",
            source=None,
            environ={},
            store=SimpleNamespace(),
        )
