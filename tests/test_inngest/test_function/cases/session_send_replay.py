"""
A completed send must keep working during replay, even if the handler's current
sessions are invalid. Otherwise, a later step's retry could fail on an event
that was already sent successfully.

Send a child, then make a later step fail once. On retry, use an invalid session
ID before replaying the send and verify that the parent still completes.
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    state = base.BaseState()
    child_runs: dict[str, str | None] = {}

    @client.create_function(
        fn_id=f"{test_name}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event=f"{event_name}/child"),
    )
    def child(ctx: inngest.ContextSync) -> None:
        assert ctx.sessions == {"conversation": "chat-1"}
        child_runs[ctx.run_id] = ctx.event.id

    def fail_once(attempt: int) -> int:
        if attempt == 0:
            raise inngest.RetryAfterError("Retry the later step", 1000)
        return attempt

    def parent_sync(ctx: inngest.ContextSync) -> dict[str, object]:
        state.run_id = ctx.run_id
        ctx.sessions["conversation"] = "chat-1" if ctx.attempt == 0 else ""
        ids = ctx.step.send_event(
            "child", inngest.Event(name=f"{event_name}/child")
        )
        attempt = ctx.step.run("later", lambda: fail_once(ctx.attempt))
        return {"ids": ids, "later_step_attempt": attempt}

    async def parent_async(ctx: inngest.Context) -> dict[str, object]:
        state.run_id = ctx.run_id
        ctx.sessions["conversation"] = "chat-1" if ctx.attempt == 0 else ""
        ids = await ctx.step.send_event(
            "child", inngest.Event(name=f"{event_name}/child")
        )

        async def later() -> int:
            return fail_once(ctx.attempt)

        attempt = await ctx.step.run("later", later)
        return {"ids": ids, "later_step_attempt": attempt}

    parent = client.create_function(
        fn_id=test_name,
        retries=1,
        trigger=inngest.TriggerEvent(event=event_name),
    )(parent_sync if is_sync else parent_async)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        result = json.loads(run.output)
        assert result["later_step_attempt"] == 1

        def check_child() -> None:
            assert len(child_runs) == 1
            assert result["ids"] == list(child_runs.values())

        await base.wait_for(check_child)

    return base.Case(fn=[parent, child], name=test_name, run_test=run_test)
