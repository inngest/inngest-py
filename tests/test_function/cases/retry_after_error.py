import datetime
import typing

import inngest
import tests.helper
from inngest._internal import const

from . import base


class _State(base.BaseState):
    fn_level_raise_1_time: typing.Optional[datetime.datetime] = None
    fn_level_retry_1_time: typing.Optional[datetime.datetime] = None
    fn_level_raise_2_time: typing.Optional[datetime.datetime] = None
    fn_level_retry_2_time: typing.Optional[datetime.datetime] = None
    step_level_raise_time: typing.Optional[datetime.datetime] = None
    step_level_retry_time: typing.Optional[datetime.datetime] = None


def create(
    client: inngest.Inngest,
    framework: const.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        retries=2,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        if state.fn_level_raise_1_time is None:
            # Raise a RetryAfterError and track what time we raised it
            state.fn_level_raise_1_time = datetime.datetime.now()
            raise inngest.RetryAfterError("fn-1", 1000)

        if state.fn_level_retry_1_time is None:
            # Track the time we retried
            state.fn_level_retry_1_time = datetime.datetime.now()

        def step_fn() -> None:
            if state.step_level_raise_time is None:
                # Raise a RetryAfterError and track what time we raised it
                state.step_level_raise_time = datetime.datetime.now()
                raise inngest.RetryAfterError(
                    "step", datetime.timedelta(seconds=1)
                )

            if state.step_level_retry_time is None:
                # Track the time we retried
                state.step_level_retry_time = datetime.datetime.now()

        step.run("step_1", step_fn)

        if state.fn_level_raise_2_time is None:
            # Raise a RetryAfterError and track what time we raised it
            state.fn_level_raise_2_time = datetime.datetime.now()
            raise inngest.RetryAfterError(
                "fn-2", datetime.datetime.now() + datetime.timedelta(seconds=1)
            )

        if state.fn_level_retry_2_time is None:
            # Track the time we retried
            state.fn_level_retry_2_time = datetime.datetime.now()

    @client.create_function(
        fn_id=fn_id,
        retries=2,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        if state.fn_level_raise_1_time is None:
            # Raise a RetryAfterError and track what time we raised it
            state.fn_level_raise_1_time = datetime.datetime.now()
            raise inngest.RetryAfterError("fn-1", 1000)

        if state.fn_level_retry_1_time is None:
            # Track the time we retried
            state.fn_level_retry_1_time = datetime.datetime.now()

        async def step_fn() -> None:
            if state.step_level_raise_time is None:
                # Raise a RetryAfterError and track what time we raised it
                state.step_level_raise_time = datetime.datetime.now()
                raise inngest.RetryAfterError(
                    "step", datetime.timedelta(seconds=1)
                )

            if state.step_level_retry_time is None:
                # Track the time we retried
                state.step_level_retry_time = datetime.datetime.now()

        await step.run("step_1", step_fn)

        if state.fn_level_raise_2_time is None:
            # Raise a RetryAfterError and track what time we raised it
            state.fn_level_raise_2_time = datetime.datetime.now()
            raise inngest.RetryAfterError(
                "fn-2", datetime.datetime.now() + datetime.timedelta(seconds=1)
            )

        if state.fn_level_retry_2_time is None:
            # Track the time we retried
            state.fn_level_retry_2_time = datetime.datetime.now()

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()

        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.fn_level_raise_1_time is not None
        assert state.fn_level_retry_1_time is not None
        assert state.step_level_raise_time is not None
        assert state.step_level_retry_time is not None
        assert state.fn_level_raise_2_time is not None
        assert state.fn_level_retry_2_time is not None

        assert (
            state.fn_level_retry_1_time - state.fn_level_raise_1_time
            < datetime.timedelta(seconds=2)
        )

        assert (
            state.step_level_retry_time - state.step_level_raise_time
            < datetime.timedelta(seconds=2)
        )

        assert (
            state.fn_level_retry_2_time - state.fn_level_raise_2_time
            < datetime.timedelta(seconds=2)
        )

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
