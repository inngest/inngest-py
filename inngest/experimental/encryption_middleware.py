"""
Encryption middleware for Inngest.

NOT STABLE! This is an experimental feature and may change in the future.
"""

from __future__ import annotations

import json
import typing

import nacl.encoding
import nacl.secret
import nacl.utils

import inngest

encryption_marker: typing.Final = "__ENCRYPTED__"


class EncryptionMiddleware(inngest.MiddlewareSync):
    """
    Middleware that encrypts and decrypts data using a symmetric key. The
    cryptography library is a dependency.
    """

    def __init__(
        self,
        client: inngest.Inngest,
        raw_request: object,
        secret_key: typing.Union[bytes, str],
    ) -> None:
        """
        Args:
        ----
            client: Inngest client.
            raw_request: Framework/platform specific request object.
            secret_key: Fernet secret key used for encryption and decryption.
        """

        super().__init__(client, raw_request)

        if isinstance(secret_key, str):
            secret_key = bytes.fromhex(secret_key)

        self._box = nacl.secret.SecretBox(secret_key)

    @classmethod
    def factory(
        cls,
        secret_key: typing.Union[bytes, str],
    ) -> typing.Callable[[inngest.Inngest, object], EncryptionMiddleware]:
        """
        Create an encryption middleware factory that can be passed to an Inngest
        client or function.

        Args:
        ----
            secret_key: Fernet secret key used for encryption and decryption.
        """

        def _factory(
            client: inngest.Inngest,
            raw_request: object,
        ) -> EncryptionMiddleware:
            return cls(client, raw_request, secret_key)

        return _factory

    def _encrypt(self, data: object) -> dict[str, typing.Union[bool, str]]:
        if isinstance(data, dict) and data.get(encryption_marker) is True:
            # Already encrypted
            return data

        byt = json.dumps(data).encode()
        ciphertext = self._box.encrypt(
            byt,
            encoder=nacl.encoding.Base64Encoder,
        )
        return {
            encryption_marker: True,
            "data": ciphertext.decode(),
        }

    def _decrypt(self, data: object) -> inngest.JSON:
        if not _is_encrypted(data) or not isinstance(data, dict):
            # Not encrypted
            return data  # type: ignore

        encrypted = data.get("data")
        if not isinstance(encrypted, str):
            return data

        byt = self._box.decrypt(
            encrypted.encode(),
            encoder=nacl.encoding.Base64Encoder,
        )
        return json.loads(byt.decode())  # type: ignore

    def _decrypt_event_data(
        self,
        data: typing.Mapping[str, inngest.JSON],
    ) -> typing.Mapping[str, inngest.JSON]:
        is_everything_encrypted = _is_encrypted(data)
        if is_everything_encrypted:
            decrypted = self._decrypt(data)
            if isinstance(decrypted, dict):
                data = decrypted
        else:
            data = {k: self._decrypt(v) for k, v in data.items()}

        return data

    def before_send_events(self, events: list[inngest.Event]) -> None:
        """
        Encrypt event data before sending it to the Inngest server.
        """

        for event in events:
            event.data = self._encrypt(event.data)

    def transform_input(
        self,
        ctx: inngest.Context,
        steps: inngest.StepMemos,
    ) -> None:
        """
        Decrypt data from the Inngest server.
        """

        for step in steps.values():
            step.data = self._decrypt(step.data)

        ctx.event.data = self._decrypt_event_data(ctx.event.data)

        for event in ctx.events:
            event.data = self._decrypt_event_data(event.data)

    def transform_output(self, result: inngest.CallResult) -> None:
        """
        Encrypt data before sending it to the Inngest server.
        """

        if result.output is not None:
            result.output = self._encrypt(result.output)


def _is_encrypted(value: object) -> bool:
    return isinstance(value, dict) and value.get(encryption_marker) is True
