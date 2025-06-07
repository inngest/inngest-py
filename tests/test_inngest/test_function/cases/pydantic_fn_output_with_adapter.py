"""
Functions can return Pydantic objects if they specify a type adapter.
"""

import json

import inngest
import pydantic
import test_core.helper
from inngest._internal import server_lib

from . import base


class _User(pydantic.BaseModel):
    name: str


class _State(base.BaseState):
    invoke_output: list[_User] = []  # noqa: RUF012


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
        fn_id=f"{fn_id}/invokee",
        output_serializer=pydantic.TypeAdapter(list[_User]),
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    def fn_receiver_sync(ctx: inngest.ContextSync) -> list[_User]:
        return [_User(name="Alice")]

    @client.create_function(
        fn_id=fn_id,
        output_serializer=pydantic.TypeAdapter(object),
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> list[_User]:
        state.run_id = ctx.run_id
        state.invoke_output = ctx.step.invoke(
            "invoke",
            function=fn_receiver_sync,
        )
        return state.invoke_output

    @client.create_function(
        fn_id=f"{fn_id}/invokee",
        output_serializer=pydantic.TypeAdapter(list[_User]),
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def fn_receiver_async(ctx: inngest.Context) -> list[_User]:
        return [_User(name="Alice")]

    @client.create_function(
        fn_id=fn_id,
        output_serializer=pydantic.TypeAdapter(object),
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> list[_User]:
        state.run_id = ctx.run_id
        state.invoke_output = await ctx.step.invoke(
            "invoke",
            function=fn_receiver_sync,
        )
        return state.invoke_output

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.invoke_output == [_User(name="Alice")]

        assert run.output is not None
        assert json.loads(run.output) == [
            {
                "name": "Alice",
            }
        ]

    if is_sync:
        fn = [fn_sync, fn_receiver_sync]
    else:
        fn = [fn_async, fn_receiver_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
