"""
Ensure that the function receives decrypted event data but does not encrypt
anything
"""

import json

import inngest
import nacl.encoding
import nacl.hash
import nacl.secret
import nacl.utils
import test_core.helper
from inngest._internal import server_lib
from inngest_encryption import EncryptionMiddleware

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
            EncryptionMiddleware.factory(_secret_key, decrypt_only=True)
        ],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> str:
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id

        def _step_1() -> str:
            return "test string"

        step_1_output = ctx.step.run("step_1", _step_1)
        assert step_1_output == "test string"

        def _step_2() -> list[inngest.JSON]:
            return [{"a": {"b": 1}}]

        step_2_output = ctx.step.run("step_2", _step_2)
        assert step_2_output == [{"a": {"b": 1}}]

        return "function output"

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            EncryptionMiddleware.factory(_secret_key, decrypt_only=True)
        ],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> str:
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id

        async def _step_1() -> str:
            return "test string"

        step_1_output = await ctx.step.run("step_1", _step_1)
        assert step_1_output == "test string"

        async def _step_2() -> list[inngest.JSON]:
            return [{"a": {"b": 1}}]

        step_2_output = await ctx.step.run("step_2", _step_2)
        assert step_2_output == [{"a": {"b": 1}}]

        return "function output"

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
        run = await test_core.helper.client.wait_for_run_status(
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

        # Ensure that step_1 output is encrypted and its value is correct
        output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert isinstance(output, dict)
        assert output.get("data") == "test string"

        # Ensure that step_2 output is encrypted and its value is correct
        output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_2",
            )
        )
        assert isinstance(output, dict)
        assert output.get("data") == [{"a": {"b": 1}}]

        assert run.output is not None
        assert json.loads(run.output) == "function output"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
