"""
Reject an experiment inside another variant before running its work. Otherwise
the inner selection step receives two conflicting experiment assignments.
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import experiment

from . import base


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    state = base.BaseState()
    inner_ran = False
    attempts: list[int] = []

    def work() -> None:
        nonlocal inner_ran
        inner_ran = True

    def sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        attempts.append(ctx.attempt)
        ctx.group.experiment(
            "outer",
            variants={
                "control": lambda: ctx.group.experiment(
                    "inner",
                    variants={"variant": lambda: ctx.step.run("work", work)},
                    select=experiment.fixed("variant"),
                )
            },
            select=experiment.fixed("control"),
        )

    async def async_fn(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        attempts.append(ctx.attempt)

        async def async_work() -> None:
            work()

        await ctx.group.experiment(
            "outer",
            variants={
                "control": lambda: ctx.group.experiment(
                    "inner",
                    variants={
                        "variant": lambda: ctx.step.run("work", async_work)
                    },
                    select=experiment.fixed("variant"),
                )
            },
            select=experiment.fixed("control"),
        )

    fn = client.create_function(
        fn_id=test_name,
        retries=1,
        trigger=inngest.TriggerEvent(event=event_name),
    )(sync if is_sync else async_fn)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id, test_core.helper.RunStatus.FAILED
        )
        assert run.output is not None
        assert (
            "Nested experiments are not supported"
            in json.loads(run.output)["message"]
        )
        assert not inner_ran
        assert set(attempts) == {0}  # Rejection must bypass configured retries.

    return base.Case(fn=fn, name=test_name, run_test=run_test)
