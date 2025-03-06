"""
Ensure that the encryption middleware can decrypt data using a fallback
decryption key. The primary key is intentionally wrong
"""

import inngest
import nacl.encoding
import nacl.hash
import nacl.secret
import nacl.utils
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental.encryption_middleware import EncryptionMiddleware

from . import base

_secret_key = "my-secret-key"


enc = base.Encryptor(
    nacl.hash.blake2b(
        _secret_key.encode("utf-8"),
        digest_size=nacl.secret.SecretBox.KEY_SIZE,
    )
)


class _State(base.BaseState):
    event: inngest.Event
    events: list[inngest.Event]


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            EncryptionMiddleware.factory(
                "invalid-secret",
                fallback_decryption_keys=[_secret_key],
            )
        ],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            EncryptionMiddleware.factory(
                "invalid-secret",
                fallback_decryption_keys=[_secret_key],
            )
        ],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id

    async def run_test(self: base.TestClass) -> None:
        # Send an event that contains an encrypted field
        self.client.send_sync(
            inngest.Event(
                name=event_name,
                data={
                    "a": 1,
                    "encrypted": enc.encrypt({"b": 2}),
                },
            )
        )

        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        # Ensure that the function receives decrypted data
        assert state.event.data == {
            "a": 1,
            "encrypted": {
                "b": 2,
            },
        }
        assert state.events[0].data == {
            "a": 1,
            "encrypted": {
                "b": 2,
            },
        }

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
