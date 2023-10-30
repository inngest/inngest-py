import asyncio

import inngest
import tests.helper

from . import base

_TEST_NAME = "client_send"


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = base.BaseState()

    @inngest.create_function_sync(
        fn_id=test_name,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(*, run_id: str, **_kwargs: object) -> None:
        state.run_id = run_id

    @inngest.create_function(
        fn_id=test_name,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(*, run_id: str, **_kwargs: object) -> None:
        state.run_id = run_id

    def run_test(_self: object) -> None:
        asyncio.run(client.send(inngest.Event(name=event_name)))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

    fn: inngest.Function | inngest.FunctionSync
    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=test_name,
    )
