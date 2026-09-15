import pytest

from app.security.secrets import InsecureCredentialBackend, KeyringCredentialStore


class FakeBackend:
    priority = 1

    def __init__(self, name: str) -> None:
        self.name = name
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_explicitly_trusted_backend_can_store_and_delete(monkeypatch) -> None:
    monkeypatch.setattr("app.security.secrets.SUPPORTED_BACKEND_TYPES", (FakeBackend,))
    store = KeyringCredentialStore(FakeBackend("test double"))

    store.set("oauth", "refresh-token")
    assert store.get("oauth") == "refresh-token"
    store.delete("oauth")
    assert store.get("oauth") is None


@pytest.mark.parametrize("spoofed_name", ["macOS Keychain", "SecretService", "PlaintextKeyring"])
def test_non_native_backend_fails_closed_even_if_its_name_looks_native(spoofed_name) -> None:
    with pytest.raises(InsecureCredentialBackend):
        KeyringCredentialStore(FakeBackend(spoofed_name))
