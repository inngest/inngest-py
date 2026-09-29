"""
Invalid bucket configuration should fail immediately, without retrying selection
or running a variant. Retries cannot fix mismatched weights or invalid names.
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import experiment

from . import base


def create(
    client: inngest.Inngest, framework: server_lib.Framework, is_sync: bool
) -> base.Case:
    name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, name)
    cases = {
        "weights": "Experiment weights must match the variant names",
        "names": "Bucket variant names must use lowercase ASCII letters and digits",
    }
    states = {case: base.BaseState() for case in cases}
    attempts: dict[str, list[int]] = {case: [] for case in cases}

    def prepare(ctx: inngest.Context | inngest.ContextSync) -> str:
        case = str(ctx.event.data["case"])
        states[case].run_id = ctx.run_id
        attempts[case].append(ctx.attempt)
        return case

    def work() -> None:
        raise AssertionError("Invalid selection must not run a variant")

    def sync(ctx: inngest.ContextSync) -> None:
        case = prepare(ctx)
        ctx.group.experiment(
            "model",
            variants={
                "control": work,
                "new_flow" if case == "names" else "variant": work,
            },
            select=experiment.bucket(
                "alice", weights={"control": 1} if case == "weights" else None
            ),
        )

    async def async_fn(ctx: inngest.Context) -> None:
        case = prepare(ctx)

        async def async_work() -> None:
            work()

        await ctx.group.experiment(
            "model",
            variants={
                "control": async_work,
                "new_flow" if case == "names" else "variant": async_work,
            },
            select=experiment.bucket(
                "alice", weights={"control": 1} if case == "weights" else None
            ),
        )

    fn = client.create_function(
        fn_id=name, retries=1, trigger=inngest.TriggerEvent(event=event_name)
    )(sync if is_sync else async_fn)

    async def run_test(self: base.TestClass) -> None:
        for case, message in cases.items():
            with self.subTest(case=case):
                self.client.send_sync(
                    inngest.Event(name=event_name, data={"case": case})
                )
                run_id = await states[case].wait_for_run_id()
                run = await test_core.helper.client.wait_for_run_status(
                    run_id, test_core.helper.RunStatus.FAILED
                )
                assert run.output is not None
                assert message in json.loads(run.output)["message"]
                assert attempts[case] == [0]

    return base.Case(fn=fn, name=name, run_test=run_test)
