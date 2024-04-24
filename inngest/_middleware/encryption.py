from __future__ import annotations

import json
import typing

import cryptography.fernet

import inngest


class EncryptionMiddleware(inngest.MiddlewareSync):
    """
    Middleware that encrypts and decrypts data using a symmetric key. The
    cryptography library is a dependency.
    """

    def __init__(
        self,
        client: inngest.Inngest,
        secret_key: typing.Union[bytes, str],
    ) -> None:
        """
        Args:
        ----
            client: Inngest client.
            secret_key: Fernet secret key used for encryption and decryption.
        """

        super().__init__(client)
        self._fernet = cryptography.fernet.Fernet(secret_key)

    @classmethod
    def factory(
        cls,
        secret_key: typing.Union[bytes, str],
    ) -> typing.Callable[[inngest.Inngest], EncryptionMiddleware]:
        """
        Create an encryption middleware factory that can be passed to an Inngest
        client or function.

        Args:
        ----
            secret_key: Fernet secret key used for encryption and decryption.
        """

        def _factory(client: inngest.Inngest) -> EncryptionMiddleware:
            return cls(client, secret_key)

        return _factory

    def transform_input(self, ctx: inngest.Context) -> inngest.Context:
        for v in ctx._steps.values():
            if isinstance(v.data, str):
                # If the data is a string then attempt decryption
                try:
                    byt = self._fernet.decrypt(v.data.encode())
                    v.data = json.loads(byt.decode())
                except cryptography.fernet.InvalidToken:
                    # If decryption failed then assume the data is not
                    # encrypted
                    pass

        return ctx

    def transform_output(self, output: inngest.Output) -> inngest.Output:
        byt = json.dumps(output.data).encode()
        output.data = self._fernet.encrypt(byt).decode()
        return output
