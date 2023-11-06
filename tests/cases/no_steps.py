import json

import inngest
import tests.helper

from . import base

_TEST_NAME = "no_steps"


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = base.BaseState()

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(*, run_id: str, **_kwargs: object) -> dict[str, object]:
        state.run_id = run_id
        return {"foo": {"bar": 1}}

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(*, run_id: str, **_kwargs: object) -> dict[str, object]:
        state.run_id = run_id
        return {"foo": {"bar": 1}}

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        output = json.loads(run.output)
        assert output == {"foo": {"bar": 1}}, output

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
