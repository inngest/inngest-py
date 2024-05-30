import typing

import inngest
import tests.helper
from inngest._internal import const

from . import base

_TEST_NAME = "event_payload"


class _State(base.BaseState):
    event: typing.Optional[inngest.Event] = None


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
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.event = ctx.event
        state.run_id = ctx.run_id

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.event = ctx.event
        state.run_id = ctx.run_id

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(
            inngest.Event(
                data={"foo": {"bar": "baz"}},
                name=event_name,
                user={"a": {"b": "c"}},
            )
        )
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.event is not None
        assert state.event.id != ""
        assert state.event.name == event_name
        assert state.event.data == {"foo": {"bar": "baz"}}
        assert state.event.ts > 0
        assert state.event.user == {"a": {"b": "c"}}

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
