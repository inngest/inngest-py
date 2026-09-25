"""
Invoked functions should inherit the caller's sessions unless explicitly
overridden or removed. Otherwise, invoking a child function could lose its
connection to the user's conversation, or keep a connection the caller removed.

Check the sessions the child actually receives after the server applies
these instructions.
"""

import datetime

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base
from .session_scenarios import parent_sessions, scenarios


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    child_event = f"{event_name}/child"
    state = base.BaseState()
    received: dict[str, dict[str, str]] = {}

    @client.create_function(
        fn_id=f"{test_name}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event=child_event),
    )
    def child(ctx: inngest.ContextSync) -> None:
        scenario = ctx.event.data["scenario"]
        assert isinstance(scenario, str)
        received[scenario] = dict(ctx.sessions)

    def parent_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        assert ctx.sessions == parent_sessions
        for case in scenarios:
            ctx.step.invoke(
                case.name,
                function=child,
                data={"scenario": case.name},
                meta=case.meta,
            )

    async def parent_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        assert ctx.sessions == parent_sessions
        for case in scenarios:
            await ctx.step.invoke(
                case.name,
                function=child,
                data={"scenario": case.name},
                meta=case.meta,
            )

    parent = client.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )(parent_sync if is_sync else parent_async)

    async def run_test(self: base.TestClass) -> None:
        # Assert what child handlers actually see, after server-side resolution.
        def children_have_expected_sessions() -> None:
            assert received == {case.name: case.expected for case in scenarios}

        received.clear()
        state.run_id = None
        self.client.send_sync(
            inngest.Event(
                name=event_name,
                data={},
                meta={"sessions": dict(parent_sessions)},
            )
        )
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        await base.wait_for(
            children_have_expected_sessions,
            timeout=datetime.timedelta(seconds=15),
        )

    return base.Case(fn=[parent, child], name=test_name, run_test=run_test)
