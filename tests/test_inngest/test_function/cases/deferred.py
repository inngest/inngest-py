"""
A deferred function receives its input after the parent finishes.
"""

import json
import typing

import inngest
import test_core.gql
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import create_defer, dev_server

from . import base


def create(
    client: inngest.Inngest, framework: server_lib.Framework, is_sync: bool
) -> base.Case:
    name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, name)
    parent_state = base.BaseState()
    child_state = base.BaseState()
    parent_finished = False

    def receive(ctx: inngest.Context | inngest.ContextSync) -> None:
        child_state.run_id = ctx.run_id
        assert parent_finished
        assert ctx.event.data == {"message": "hello"}

    target = create_defer(client, fn_id=f"{name}-child", retries=0)(
        receive if is_sync else base.asyncify(receive)
    )

    def run(ctx: inngest.Context | inngest.ContextSync) -> str:
        nonlocal parent_finished
        parent_state.run_id = ctx.run_id
        ctx.defer("child", function=target, data={"message": "hello"})
        parent_finished = True
        return "parent-result"

    parent = client.create_function(
        fn_id=name, retries=0, trigger=inngest.TriggerEvent(event=event_name)
    )(run if is_sync else base.asyncify(run))

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        parent_id = await parent_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            parent_id, test_core.helper.RunStatus.COMPLETED
        )
        child_id = await child_state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            child_id, test_core.helper.RunStatus.COMPLETED
        )

        # Scheduling deferred work must preserve the parent's return value.
        # The trace API resolves RunComplete; legacy run.output may contain
        # the full opcode envelope instead.
        gql = test_core.gql.Client(f"{dev_server.server.origin}/v0/gql")
        response = await gql.query(
            test_core.gql.Query(
                "query($id: String!) { run(runID: $id) { trace { outputID } } }",
                {"id": parent_id},
            )
        )
        assert isinstance(response, test_core.gql.Response)
        data = typing.cast(dict[str, typing.Any], response.data)
        response = await gql.query(
            test_core.gql.Query(
                "query($id: String!) { runTraceSpanOutputByID(outputID: $id) { data } }",
                {"id": data["run"]["trace"]["outputID"]},
            )
        )
        assert isinstance(response, test_core.gql.Response)
        data = typing.cast(dict[str, typing.Any], response.data)
        assert (
            json.loads(data["runTraceSpanOutputByID"]["data"])
            == "parent-result"
        )

    return base.Case(fn=[parent, target], name=name, run_test=run_test)
