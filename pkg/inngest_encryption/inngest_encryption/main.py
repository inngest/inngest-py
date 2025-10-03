"""
Encryption middleware for Inngest.
"""

from __future__ import annotations

import json
import typing

import inngest
import nacl.encoding
import nacl.hash
import nacl.secret
import nacl.utils
from inngest._internal import server_lib

# Marker to indicate that the data is encrypted
_encryption_marker: typing.Final = "__ENCRYPTED__"

# Marker to indicate which strategy was used to encrypt. This is useful for
# knowing whether the official encryption middleware was used
_strategy_marker: typing.Final = "__STRATEGY__"

_strategy_identifier: typing.Final = "inngest/libsodium"

# Automatically encrypt and decrypt this field in event data
_default_event_encryption_field: typing.Final = "encrypted"


def _ensure_key_bytes(secret_key: bytes | str) -> bytes:
    if isinstance(secret_key, str):
        return nacl.hash.generichash(
            secret_key.encode("utf-8"),
            digest_size=nacl.secret.SecretBox.KEY_SIZE,
        )

    return secret_key


class EncryptionMiddleware(inngest.MiddlewareSync):
    """
    Middleware that encrypts and decrypts data using a symmetric key. The
    cryptography library is a dependency.
    """

    def __init__(
        self,
        client: inngest.Inngest,
        raw_request: object,
        secret_key: bytes | str,
        *,
        decrypt_only: bool = False,
        event_encryption_field: str = _default_event_encryption_field,
        fallback_decryption_keys: list[bytes | str] | None = None,
    ) -> None:
        """
        Args:
        ----
            client: Inngest client.
            raw_request: Framework/platform specific request object.
            secret_key: Secret key used for encryption and decryption.
            decrypt_only: Only decrypt data (do not encrypt).
            event_encryption_field: Automatically encrypt and decrypt this field in event and invoke data.
            fallback_decryption_keys: Fallback secret keys used for decryption.
        """

        super().__init__(client, raw_request)

        self._box = nacl.secret.SecretBox(
            _ensure_key_bytes(secret_key),
            encoder=nacl.encoding.HexEncoder,
        )

        self._decrypt_only = decrypt_only
        self._event_encryption_field = event_encryption_field

        self._fallback_decryption_boxes = [
            nacl.secret.SecretBox(
                _ensure_key_bytes(fallback_key),
                encoder=nacl.encoding.HexEncoder,
            )
            for fallback_key in (fallback_decryption_keys or [])
        ]

    @classmethod
    def factory(
        cls,
        secret_key: bytes | str,
        *,
        decrypt_only: bool = False,
        event_encryption_field: str = _default_event_encryption_field,
        fallback_decryption_keys: list[bytes | str] | None = None,
    ) -> typing.Callable[[inngest.Inngest, object], EncryptionMiddleware]:
        """
        Create an encryption middleware factory that can be passed to an Inngest
        client or function.

        Args:
        ----
            secret_key: Fernet secret key used for encryption and decryption.
            decrypt_only: Only decrypt data (do not encrypt).
            event_encryption_field: Automatically encrypt and decrypt this field in event and invoke data.
            fallback_decryption_keys: Fallback secret keys used for decryption.
        """

        def _factory(
            client: inngest.Inngest,
            raw_request: object,
        ) -> EncryptionMiddleware:
            return cls(
                client,
                raw_request,
                secret_key,
                decrypt_only=decrypt_only,
                event_encryption_field=event_encryption_field,
                fallback_decryption_keys=fallback_decryption_keys,
            )

        return _factory

    def _encrypt(self, data: object) -> dict[str, bool | str]:
        if isinstance(data, dict) and data.get(_encryption_marker) is True:
            # Already encrypted
            self.client.logger.warning(
                "Skipping encryption since data is already encrypted"
            )
            return data

        byt = json.dumps(data).encode()
        ciphertext = self._box.encrypt(
            byt,
            encoder=nacl.encoding.Base64Encoder,
        )
        return {
            _encryption_marker: True,
            _strategy_marker: _strategy_identifier,
            "data": ciphertext.decode(),
        }

    def _decrypt(self, data: object) -> inngest.JSON:
        if not _is_encrypted(data) or not isinstance(data, dict):
            # Not encrypted
            return data  # type: ignore

        encrypted = data.get("data")
        if not isinstance(encrypted, str):
            return data

        for box in [self._box, *self._fallback_decryption_boxes]:
            try:
                byt = box.decrypt(
                    encrypted.encode(),
                    encoder=nacl.encoding.Base64Encoder,
                )

                return json.loads(byt.decode())  # type: ignore
            except Exception:
                continue

        raise Exception("Failed to decrypt data")

    def _decrypt_event_data(
        self,
        data: typing.Mapping[str, inngest.JSON],
    ) -> typing.Mapping[str, inngest.JSON]:
        # Sort with expected encryption field first, since it's the most likely
        # to be encrypted
        keys = sorted(
            data.keys(), key=lambda k: k != self._event_encryption_field
        )

        if _is_encrypted(data):
            # Event data has top-level encryption. However, there may also be
            # unencrypted fields (like "_inngest" if this is an invoke event).

            decrypted = self._decrypt(data)
            if not isinstance(decrypted, dict):
                raise Exception("decrypted data is not a dict")

            # Need to type cast because mypy thinks it's a `dict[str, object]`.
            decrypted = typing.cast(
                typing.Mapping[str, inngest.JSON], decrypted
            )

            # This should be empty if this isn't an invoke event.
            unencrypted_data = {
                k: v
                for k, v in data.items()
                if k not in (_encryption_marker, _strategy_marker, "data")
            }

            return {
                **unencrypted_data,
                **decrypted,
            }

        # Iterate over all the keys, decrypting the first encrypted field found.
        # It's possible that the event producer uses a different encryption
        # field
        for k in keys:
            encrypted = data.get(k)
            if not _is_encrypted(encrypted):
                continue

            return {
                **data,
                k: self._decrypt(encrypted),
            }

        return data

    def before_send_events(self, events: list[inngest.Event]) -> None:
        """
        Encrypt event data before sending it to the Inngest server.
        """

        if self._decrypt_only:
            return

        for event in events:
            decrypted = event.data.get(self._event_encryption_field)
            if decrypted is not None:
                event.data = {
                    **event.data,
                    self._event_encryption_field: self._encrypt(decrypted),
                }

    def transform_input(
        self,
        ctx: inngest.Context | inngest.ContextSync,
        function: inngest.Function[typing.Any],
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

    def transform_output(self, result: inngest.TransformOutputResult) -> None:
        """
        Encrypt data before sending it to the Inngest server.
        """

        if self._decrypt_only:
            return

        if result.has_output():
            result.output = self._encrypt(result.output)

        # Encrypt invoke data if present.
        if (
            result.step is not None
            and result.step.op is server_lib.Opcode.INVOKE
            and result.step.opts is not None
        ):
            payload = result.step.opts.get("payload", {})
            if isinstance(payload, dict):
                data = payload.get("data")
                if (
                    isinstance(data, dict)
                    and self._event_encryption_field in data
                ):
                    payload["data"] = {
                        **data,
                        self._event_encryption_field: self._encrypt(
                            data[self._event_encryption_field]
                        ),
                    }
                    result.step.opts["payload"] = payload


def _is_encrypted(value: object) -> bool:
    if not isinstance(value, dict):
        return False

    if value.get(_encryption_marker) is not True:
        return False

    if value.get(_strategy_marker) != _strategy_identifier:
        return False

    return True
