import json
import typing

import nacl.encoding
import nacl.secret
import nacl.utils

import inngest
import tests.helper
from inngest._internal import const
from inngest.experimental.encryption_middleware import EncryptionMiddleware

from . import base

_TEST_NAME = "encryption_middleware"

_secret_key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
_box = nacl.secret.SecretBox(_secret_key)


def _encrypt(data: object) -> dict[str, typing.Union[bool, str]]:
    """
    Encrypt data the way middleware would.
    """

    byt = json.dumps(data).encode()
    ciphertext = _box.encrypt(
        byt,
        encoder=nacl.encoding.Base64Encoder,
    )
    return {
        "__ENCRYPTED__": True,
        "data": ciphertext.decode(),
    }


def _decrypt(data: bytes) -> object:
    return json.loads(
        _box.decrypt(
            data,
            encoder=nacl.encoding.Base64Encoder,
        ).decode()
    )


class _State(base.BaseState):
    event: inngest.Event
    events: list[inngest.Event]


def create(
    client: inngest.Inngest,
    framework: const.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        middleware=[EncryptionMiddleware.factory(_secret_key)],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id

        def _step_1() -> str:
            return "test string"

        step_1_output = step.run("step_1", _step_1)
        assert step_1_output == "test string"

        def _step_2() -> list[inngest.JSON]:
            return [{"a": {"b": 1}}]

        step_2_output = step.run("step_2", _step_2)
        assert step_2_output == [{"a": {"b": 1}}]

        return "function output"

    @client.create_function(
        fn_id=fn_id,
        middleware=[EncryptionMiddleware.factory(_secret_key)],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> str:
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id

        def _step_1() -> str:
            return "test string"

        step_1_output = await step.run("step_1", _step_1)
        assert step_1_output == "test string"

        def _step_2() -> list[inngest.JSON]:
            return [{"a": {"b": 1}}]

        step_2_output = await step.run("step_2", _step_2)
        assert step_2_output == [{"a": {"b": 1}}]

        return "function output"

    def run_test(self: base.TestClass) -> None:
        # Send an event that contains an encrypted field
        self.client.send_sync(
            inngest.Event(
                name=event_name,
                data={
                    "a": 1,
                    "b": _encrypt(2),
                },
            )
        )

        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        # Ensure that the function receives decrypted data
        assert state.event.data == {
            "a": 1,
            "b": 2,
        }
        assert state.events[0].data == {
            "a": 1,
            "b": 2,
        }

        # Ensure that step_1 output is encrypted and its value is correct
        output = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert isinstance(output, dict)
        data = output.get("data")
        assert isinstance(data, dict)
        assert _decrypt(data["data"]) == "test string"

        # Ensure that step_2 output is encrypted and its value is correct
        output = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_2",
            )
        )
        assert isinstance(output, dict)
        data = output.get("data")
        assert isinstance(data, dict)
        assert _decrypt(data["data"]) == [{"a": {"b": 1}}]

        assert run.output is not None
        run_output = json.loads(run.output)
        assert isinstance(run_output, dict)
        assert _decrypt(run_output["data"]) == "function output"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
