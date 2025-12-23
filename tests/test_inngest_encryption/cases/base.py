import dataclasses
import json
import typing

import inngest
import nacl.encoding
import nacl.secret
import test_core
from inngest._internal import server_lib
from test_core import base

BaseState = base.BaseState
create_test_name = base.create_test_name
wait_for = base.wait_for


class TestClass(typing.Protocol):
    client: inngest.Inngest


@dataclasses.dataclass
class Case:
    fn: inngest.Function[typing.Any] | list[inngest.Function[typing.Any]]
    name: str
    run_test: typing.Callable[[TestClass], typing.Awaitable[None]]


def create_event_name(framework: server_lib.Framework, test_name: str) -> str:
    return test_core.worker_suffix(f"{framework.value}/{test_name}")


class Encryptor:
    def __init__(self, secret_key: bytes) -> None:
        self._box = nacl.secret.SecretBox(
            secret_key, encoder=nacl.encoding.HexEncoder
        )

    def encrypt(self, data: object) -> dict[str, bool | str]:
        """
        Encrypt data the way middleware would.
        """

        byt = json.dumps(data).encode()
        ciphertext = self._box.encrypt(
            byt,
            encoder=nacl.encoding.Base64Encoder,
        )
        return {
            "__ENCRYPTED__": True,
            "__STRATEGY__": "inngest/libsodium",
            "data": ciphertext.decode(),
        }

    def decrypt(self, data: bytes) -> object:
        return json.loads(
            self._box.decrypt(
                data,
                encoder=nacl.encoding.Base64Encoder,
            ).decode()
        )
