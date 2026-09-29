"""
User feedback can arrive after a function finishes. Scores must attach to the
original run or named step, and updating one score must preserve other scores.
Read the stored trace metadata to verify the result, not just HTTP success.
"""

import datetime

import inngest
import pydantic
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import dev_server
from test_core import gql

from . import base


class _Metadata(pydantic.BaseModel):
    kind: str
    values: dict[str, object]


class _Span(pydantic.BaseModel):
    name: str
    metadata: list[_Metadata]

    def scores(self) -> dict[str, object]:
        return {
            name: value
            for entry in self.metadata
            if entry.kind == "inngest.score"
            for name, value in entry.values.items()
        }


class _Trace(_Span):
    children: list[_Span] = pydantic.Field(alias="childrenSpans")


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    state = base.BaseState()

    def sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        ctx.step.run("answer", lambda: "Here is your answer")

    async def async_fn(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        async def answer() -> str:
            return "Here is your answer"

        await ctx.step.run("answer", answer)

    fn = client.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )(sync if is_sync else async_fn)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id, test_core.helper.RunStatus.COMPLETED
        )

        # A later correction replaces quality without erasing approved. Using
        # approved on both targets also verifies that step and run scores
        # differ.
        updates: list[tuple[str, bool | float, str | None]] = [
            ("approved", False, None),
            ("quality", 0.25, None),
            ("quality", 0.75, None),
            ("approved", True, "answer"),
        ]
        for name, value, step_id in updates:
            if is_sync:
                self.client.score_sync(
                    run_id=run_id,
                    step_id=step_id,
                    name=name,
                    value=value,
                )
            else:
                await self.client.score(
                    run_id=run_id,
                    step_id=step_id,
                    name=name,
                    value=value,
                )

        async def check_scores() -> None:
            response = await gql.Client(
                f"{dev_server.server.origin}/v0/gql"
            ).query(
                gql.Query(
                    """query($runID: String!) {
                    run(runID: $runID) {
                        trace {
                            name metadata { kind values }
                            childrenSpans { name metadata { kind values } }
                        }
                    }
                }""",
                    {"runID": run_id},
                )
            )
            assert not isinstance(response, gql.Error), response
            run = response.data["run"]
            assert isinstance(run, dict)
            trace = _Trace.model_validate(run["trace"])
            assert trace.scores() == {
                "approved": {"value": False},
                "quality": {"value": 0.75},
            }
            # The trace can expose score metadata on a separate span for the
            # same step, so inspect every span named "answer".
            answer_scores = [
                span.scores()
                for span in trace.children
                if span.name == "answer" and span.scores()
            ]
            assert answer_scores == [{"approved": {"value": True}}]

        await base.wait_for(
            check_scores, timeout=datetime.timedelta(seconds=15)
        )

    return base.Case(fn=fn, name=test_name, run_test=run_test)
