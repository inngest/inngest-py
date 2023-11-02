import datetime

import inngest
import tests.helper

from . import base

_TEST_NAME = "sleep"


class _State(base.BaseState):
    after_sleep: datetime.datetime | None = None
    before_sleep: datetime.datetime | None = None

    def is_done(self) -> bool:
        return self.after_sleep is not None and self.before_sleep is not None


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *,
        run_id: str,
        step: inngest.StepSync,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        if state.before_sleep is None:
            state.before_sleep = datetime.datetime.now()

        step.sleep("zzz", datetime.timedelta(seconds=2))

        if state.after_sleep is None:
            state.after_sleep = datetime.datetime.now()

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *,
        run_id: str,
        step: inngest.Step,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        if state.before_sleep is None:
            state.before_sleep = datetime.datetime.now()

        await step.sleep("zzz", datetime.timedelta(seconds=2))

        if state.after_sleep is None:
            state.after_sleep = datetime.datetime.now()

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.after_sleep is not None and state.before_sleep is not None
        assert state.after_sleep - state.before_sleep >= datetime.timedelta(
            seconds=2
        )

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
