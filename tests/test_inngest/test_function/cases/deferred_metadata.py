"""
Deferred handlers receive parent information separately from input data.

Sessions inherit by default; explicit overrides and removals are resolved by
the server. Experiment references reach the deferred handler unchanged.
"""

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import create_defer, experiment

from . import base


def create(
    client: inngest.Inngest, framework: server_lib.Framework, is_sync: bool
) -> base.Case:
    name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, name)
    parent_state = base.BaseState()
    received: dict[str, str] = {}
    ref = experiment.ExperimentRef(experiment_name="model", variant="control")
    expected: dict[str, dict[str, str]] = {
        "inherited": {"conversation": "chat-1", "user": "alice"},
        "overridden": {"conversation": "chat-2"},
        "cleared": {},
    }

    def receive(ctx: inngest.Context | inngest.ContextSync) -> None:
        label = ctx.event.data["label"]
        assert isinstance(label, str)
        received[label] = ctx.run_id
        assert ctx.event.data == {"label": label}
        assert ctx.events[0].data == ctx.event.data
        assert len(ctx.parents) == 1
        assert ctx.parents[0].fn_slug == f"{client.app_id}-{name}"
        assert ctx.parents[0].run_id == parent_state.run_id
        assert ctx.parents[0].experiment == ref
        assert ctx.sessions == expected[label]

    target = create_defer(client, fn_id=f"{name}-child", retries=0)(
        receive if is_sync else base.asyncify(receive)
    )

    def run(ctx: inngest.Context | inngest.ContextSync) -> None:
        parent_state.run_id = ctx.run_id
        ctx.defer(
            "inherited",
            function=target,
            data={"label": "inherited"},
            experiment=ref,
        )
        ctx.defer(
            "overridden",
            function=target,
            data={"label": "overridden"},
            experiment=ref,
            meta={"sessions": {"conversation": "chat-2", "user": None}},
        )
        ctx.defer(
            "cleared",
            function=target,
            data={"label": "cleared"},
            experiment=ref,
            meta={"sessions": None},
        )

    parent = client.create_function(
        fn_id=name, retries=0, trigger=inngest.TriggerEvent(event=event_name)
    )(run if is_sync else base.asyncify(run))

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(
            inngest.Event(
                name=event_name,
                meta={"sessions": {"conversation": "chat-1", "user": "alice"}},
            )
        )
        parent_id = await parent_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            parent_id, test_core.helper.RunStatus.COMPLETED
        )

        def children_started() -> None:
            assert set(received) == set(expected)

        await base.wait_for(children_started)
        for run_id in received.values():
            await test_core.helper.client.wait_for_run_status(
                run_id, test_core.helper.RunStatus.COMPLETED
            )

    return base.Case(fn=[parent, target], name=name, run_test=run_test)
