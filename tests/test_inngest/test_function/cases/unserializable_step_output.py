import json
import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    error: typing.Optional[BaseException] = None


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

        class Foo:
            pass

        def step_1() -> Foo:
            return Foo()

        try:
            ctx.step.run(
                "step_1",
                step_1,  # type: ignore[type-var]
            )
        except BaseException as err:
            state.error = err
            raise

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        class Foo:
            pass

        async def step_1() -> Foo:
            return Foo()

        await ctx.step.run(  # type: ignore[call-arg]
            "step_1",
            step_1,  # type: ignore[type-var]
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)

        assert output == {
            "code": "output_unserializable",
            "message": '"step_1" returned unserializable data',
            "name": "OutputUnserializableError",
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
