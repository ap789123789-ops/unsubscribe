from typing import Protocol

import keyring
from keyring.backends.macOS import Keyring as MacOSKeyring
from keyring.backends.SecretService import Keyring as SecretServiceKeyring
from keyring.errors import PasswordDeleteError

SUPPORTED_BACKEND_TYPES: tuple[type[object], ...] = (MacOSKeyring, SecretServiceKeyring)


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class InsecureCredentialBackend(RuntimeError):
    pass


class KeyringCredentialStore:
    service_name = "gmail-unsubscribe-agent"

    def __init__(self, backend: CredentialBackend | None = None) -> None:
        self._backend = backend or keyring.get_keyring()
        if not isinstance(self._backend, SUPPORTED_BACKEND_TYPES):
            raise InsecureCredentialBackend(
                "A supported macOS Keychain or Linux Secret Service backend is required"
            )

    def get(self, key: str) -> str | None:
        return self._backend.get_password(self.service_name, key)

    def set(self, key: str, value: str) -> None:
        self._backend.set_password(self.service_name, key, value)

    def delete(self, key: str) -> None:
        try:
            self._backend.delete_password(self.service_name, key)
        except PasswordDeleteError:
            return
