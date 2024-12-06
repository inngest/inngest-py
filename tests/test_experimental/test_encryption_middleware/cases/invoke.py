"""
Ensure that invoke works.
"""

import nacl.encoding
import nacl.hash
import nacl.secret
import nacl.utils

import inngest
import tests.helper
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
        fn_id=f"{fn_id}/child",
        middleware=[EncryptionMiddleware.factory(_secret_key)],
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    def child_fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        return f"Hello, {ctx.event.data['name']}!"

    @client.create_function(
        fn_id=fn_id,
        middleware=[EncryptionMiddleware.factory(_secret_key)],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        result = step.invoke(
            "invoke",
            function=child_fn_sync,
            data={"name": "Alice"},
        )
        assert isinstance(result, str)
        assert result == "Hello, Alice!"

    @client.create_function(
        fn_id=f"{fn_id}/child",
        middleware=[EncryptionMiddleware.factory(_secret_key)],
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def child_fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> str:
        return f"Hello, {ctx.event.data['name']}!"

    @client.create_function(
        fn_id=fn_id,
        middleware=[EncryptionMiddleware.factory(_secret_key)],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        result = step.invoke(
            "invoke",
            function=child_fn_sync,
            data={"name": "Alice"},
        )
        assert isinstance(result, str)
        assert result == "Hello, Alice!"

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

    if is_sync:
        fn = [child_fn_sync, fn_sync]
    else:
        fn = [child_fn_async, fn_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
