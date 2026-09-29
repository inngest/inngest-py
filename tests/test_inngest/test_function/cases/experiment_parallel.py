"""
Parallel experiments must retain separate attribution through execution.
"""

import json
import typing

import inngest
import test_core.gql
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import dev_server, experiment

from . import base


def create(
    client: inngest.Inngest, framework: server_lib.Framework, is_sync: bool
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    state = base.BaseState()

    def sync(ctx: inngest.ContextSync) -> tuple[str, ...]:
        state.run_id = ctx.run_id

        def run(name: str) -> str:
            return ctx.group.experiment(
                name,
                variants={
                    "control": lambda: ctx.step.run(
                        name + "-work", lambda: name
                    )
                },
                select=experiment.fixed("control"),
            ).result

        return ctx.group.parallel((lambda: run("first"), lambda: run("second")))

    async def async_fn(ctx: inngest.Context) -> tuple[str, ...]:
        state.run_id = ctx.run_id

        async def run(name: str) -> str:
            async def work() -> str:
                return name

            return (
                await ctx.group.experiment(
                    name,
                    variants={
                        "control": lambda: ctx.step.run(name + "-work", work)
                    },
                    select=experiment.fixed("control"),
                )
            ).result

        return await ctx.group.parallel(
            (lambda: run("first"), lambda: run("second"))
        )

    fn = client.create_function(
        fn_id=test_name, trigger=inngest.TriggerEvent(event=event_name)
    )(sync if is_sync else async_fn)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id, test_core.helper.RunStatus.COMPLETED
        )
        assert run.output is not None
        assert json.loads(run.output) == ["first", "second"]

        async def check_attribution() -> None:
            response = await test_core.gql.Client(
                f"{dev_server.server.origin}/v0/gql"
            ).query(
                test_core.gql.Query(
                    """query($id: String!) {
                        run(runID: $id) {
                            trace {
                                childrenSpans { name metadata { kind scope values } }
                            }
                        }
                    }""",
                    {"id": run_id},
                )
            )
            assert isinstance(response, test_core.gql.Response), response
            data = typing.cast(dict[str, typing.Any], response.data)
            attribution = {
                span["name"]: item
                for span in data["run"]["trace"]["childrenSpans"]
                for item in typing.cast(
                    list[dict[str, typing.Any]], span["metadata"] or []
                )
                if item["kind"] == "inngest.experiment"
            }
            for name in ("first", "second"):
                item = attribution[name + "-work"]
                assert item["scope"] == "step"
                assert item["values"]["name"] == name
                assert item["values"]["variant"] == "control"
                assert item["values"]["selection_strategy"] == "fixed"

        await base.wait_for(check_attribution)

    return base.Case(fn=fn, name=test_name, run_test=run_test)
