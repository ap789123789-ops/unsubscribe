import base64
import json
import os
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.gmail.protocols import CredentialStore


class PayloadKeyUnavailable(RuntimeError):
    pass


class PayloadCipher:
    key_name = "action-payload-aes256-v1"
    schema_version = 1

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Payload encryption requires a 256-bit key")
        self._cipher = AESGCM(key)

    @classmethod
    def from_credential_store(cls, store: CredentialStore) -> "PayloadCipher":
        try:
            encoded = store.get(cls.key_name)
        except Exception as error:
            raise PayloadKeyUnavailable(
                "The action encryption key could not be read securely"
            ) from error
        if encoded is None:
            key = AESGCM.generate_key(bit_length=256)
            try:
                store.set(cls.key_name, base64.urlsafe_b64encode(key).decode("ascii"))
            except Exception as error:
                raise PayloadKeyUnavailable(
                    "The action encryption key could not be stored securely"
                ) from error
            return cls(key)
        try:
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
            return cls(key)
        except (ValueError, UnicodeError) as error:
            raise PayloadKeyUnavailable("The action encryption key is invalid") from error

    def encrypt(self, action_id: UUID | str, payload: dict[str, Any]) -> bytes:
        nonce = os.urandom(12)
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = self._cipher.encrypt(nonce, plaintext, self._aad(action_id))
        envelope = {
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "version": self.schema_version,
        }
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()

    def decrypt(self, action_id: UUID | str, envelope: bytes) -> dict[str, Any]:
        try:
            encoded = json.loads(envelope)
            if encoded["version"] != self.schema_version:
                raise ValueError("Unsupported encrypted payload version")
            nonce = base64.urlsafe_b64decode(encoded["nonce"])
            ciphertext = base64.urlsafe_b64decode(encoded["ciphertext"])
            plaintext = self._cipher.decrypt(nonce, ciphertext, self._aad(action_id))
            decoded = json.loads(plaintext)
        except (InvalidTag, KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("Encrypted action payload could not be authenticated") from error
        if not isinstance(decoded, dict):
            raise ValueError("Encrypted action payload has the wrong shape")
        return decoded

    def _aad(self, action_id: UUID | str) -> bytes:
        return f"unsubscribe-action:{action_id}:v{self.schema_version}".encode()
