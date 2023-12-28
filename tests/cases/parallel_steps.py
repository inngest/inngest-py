import json
import unittest.mock

import inngest
import tests.helper

from . import base

_TEST_NAME = "parallel_steps"


class _State(base.BaseState):
    request_counter = 0
    step_1a_counter = 0
    step_1b_counter = 0


def create(
    client: inngest.Inngest,
    framework: str,
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
    ) -> tuple[int | list[str], ...]:
        state.run_id = ctx.run_id
        state.request_counter += 1

        def _step_1a() -> int:
            state.step_1a_counter += 1
            return 1

        def _step_1b() -> int:
            state.step_1b_counter += 1
            return 2

        return step.parallel(
            (
                lambda: step.run("1a", _step_1a),
                lambda: step.run("1b", _step_1b),
                lambda: step.send_event(
                    "send", events=inngest.Event(name="noop")
                ),
            )
        )

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> tuple[int | list[str] | None, ...]:
        state.run_id = ctx.run_id
        state.request_counter += 1

        def _step_1a() -> int:
            state.step_1a_counter += 1
            return 1

        def _step_1b() -> int:
            state.step_1b_counter += 1
            return 2

        return await step.parallel(
            (
                lambda: step.run("1a", _step_1a),
                lambda: step.run("1b", _step_1b),
                lambda: step.send_event(
                    "send", events=inngest.Event(name="noop")
                ),
            )
        )

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        def assert_request_count() -> None:
            # Not sure the best way to test that parallelism happened, so we'll
            # assert that the number of requests is greater than the number of
            # steps.
            #
            # The request count varies for some reason, so asserting an exact
            # number (instead of >) results in flakey tests. We should find out
            # why, but in the meantime this works.
            assert state.request_counter > 4, state.request_counter

        base.wait_for(assert_request_count)

        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        output = json.loads(run.output)
        assert output == [1, 2, [unittest.mock.ANY]], output

        assert state.step_1a_counter == 1, state.step_1a_counter
        assert state.step_1b_counter == 1, state.step_1b_counter

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
