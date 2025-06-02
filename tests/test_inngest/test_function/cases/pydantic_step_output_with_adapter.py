"""
Steps can return Pydantic objects if they specify a type adapter.
"""

import inngest
import pydantic
import test_core.helper
from inngest._internal import server_lib

from . import base


class _User(pydantic.BaseModel):
    name: str


class _State(base.BaseState):
    step_object_output: _User | None = None
    step_none_output: _User | None = None
    step_list_output: list[_User] | None = None


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
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        def step_object(name: str) -> _User:
            return _User(name=name)

        state.step_object_output = ctx.step.run(
            "object",
            step_object,
            "Alice",
            type_adapter=_User,
        )

        def step_none() -> _User | None:
            return None

        state.step_none_output = ctx.step.run(
            "none",
            step_none,
            type_adapter=pydantic.TypeAdapter(_User | None),
        )

        def step_list() -> list[_User]:
            return [_User(name="Alice")]

        state.step_list_output = ctx.step.run(
            "list",
            step_list,
            type_adapter=pydantic.TypeAdapter(list[_User]),
        )

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        async def step_object(name: str) -> _User:
            return _User(name=name)

        state.step_object_output = await ctx.step.run(
            "object",
            step_object,
            "Alice",
            type_adapter=_User,
        )

        async def step_none() -> _User | None:
            return None

        state.step_none_output = await ctx.step.run(
            "none",
            step_none,
            type_adapter=pydantic.TypeAdapter(_User | None),
        )

        async def step_list() -> list[_User]:
            return [_User(name="Alice")]

        state.step_list_output = await ctx.step.run(
            "list",
            step_list,
            type_adapter=pydantic.TypeAdapter(list[_User]),
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.COMPLETED,
        )

        assert isinstance(state.step_object_output, _User)
        assert state.step_object_output.name == "Alice"

        assert state.step_none_output is None

        assert isinstance(state.step_list_output, list)
        assert len(state.step_list_output) == 1
        assert isinstance(state.step_list_output[0], _User)
        assert state.step_list_output[0].name == "Alice"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
