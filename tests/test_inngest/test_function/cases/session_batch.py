"""
A batch and its child events inherit only sessions shared by every event.

For example, events from the same user but different conversations share the
user session, but neither conversation. Keeping either conversation would
incorrectly associate work for the whole batch with just one conversation.
"""

import datetime

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
    parent_sessions: dict[str, str] | None = None
    child_sessions: dict[str, str] | None = None

    @client.create_function(
        fn_id=f"{test_name}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event=f"{event_name}/child"),
    )
    def child(ctx: inngest.ContextSync) -> None:
        nonlocal child_sessions
        child_sessions = dict(ctx.sessions)

    def parent_sync(ctx: inngest.ContextSync) -> None:
        nonlocal parent_sessions
        state.run_id = ctx.run_id
        assert len(ctx.events) == 2
        parent_sessions = dict(ctx.sessions)
        ctx.step.send_event("child", inngest.Event(name=f"{event_name}/child"))

    async def parent_async(ctx: inngest.Context) -> None:
        nonlocal parent_sessions
        state.run_id = ctx.run_id
        assert len(ctx.events) == 2
        parent_sessions = dict(ctx.sessions)
        await ctx.step.send_event(
            "child", inngest.Event(name=f"{event_name}/child")
        )

    parent = client.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
        batch_events=inngest.Batch(
            max_size=2, timeout=datetime.timedelta(seconds=2)
        ),
    )(parent_sync if is_sync else parent_async)

    async def run_test(self: base.TestClass) -> None:
        nonlocal parent_sessions, child_sessions
        first = inngest.Event(
            name=event_name,
            meta={
                "sessions": {
                    "user": "alice",
                    "conversation": "chat-1",
                    "request": "first-only",
                }
            },
        )
        second = inngest.Event(
            name=event_name,
            meta={"sessions": {"user": "alice", "conversation": "chat-2"}},
        )
        cases: list[tuple[str, list[inngest.Event], dict[str, str]]] = [
            ("different conversations", [first, second], {"user": "alice"}),
            ("reversed order", [second, first], {"user": "alice"}),
            (
                "one event without sessions",
                [first, inngest.Event(name=event_name)],
                {},
            ),
        ]
        for description, events, expected in cases:
            with self.subTest(case=description):
                parent_sessions = None
                child_sessions = None
                state.run_id = None
                self.client.send_sync(events)
                run_id = await state.wait_for_run_id()
                await test_core.helper.client.wait_for_run_status(
                    run_id,
                    test_core.helper.RunStatus.COMPLETED,
                )

                def check_sessions() -> None:
                    assert parent_sessions == expected, description
                    assert child_sessions == expected, description

                await base.wait_for(
                    check_sessions, timeout=datetime.timedelta(seconds=15)
                )

    return base.Case(fn=[parent, child], name=test_name, run_test=run_test)
