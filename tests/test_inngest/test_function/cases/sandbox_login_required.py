"""
A sandbox API error fails its durable step on the first attempt, and the
replay raises the same SandboxError. The Dev Server proxies sandboxes to
Inngest Cloud and rejects them here, since tests don't run `inngest login`.
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental.sandbox import SandboxError

from . import base


class _State(base.BaseState):
    create_calls: int = 0


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = test_name
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        retries=2,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> object:
        state.run_id = ctx.run_id
        try:
            sandbox = ctx.step.sandbox.create(
                "create", name=ctx.run_id, vcpu=1, memory_mb=1024
            )
        except SandboxError as err:
            return {
                "action": err.action,
                "attempt": ctx.attempt,
                "code": err.code,
                "retryable": err.retryable,
                "status": err.status,
            }
        # Unexpected, but don't leave the sandbox running.
        sandbox.destroy("destroy")
        return None

    @client.create_function(
        fn_id=fn_id,
        retries=2,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> object:
        state.run_id = ctx.run_id
        try:
            sandbox = await ctx.step.sandbox.create(
                "create", name=ctx.run_id, vcpu=1, memory_mb=1024
            )
        except SandboxError as err:
            return {
                "action": err.action,
                "attempt": ctx.attempt,
                "code": err.code,
                "retryable": err.retryable,
                "status": err.status,
            }
        # Unexpected, but don't leave the sandbox running.
        await sandbox.destroy("destroy")
        return None

    async def run_test(self: base.TestClass) -> None:
        # What the Dev Server returns for this request outside a function.
        try:
            sandbox = await self.client.sandboxes.create(
                name="direct", vcpu=1, memory_mb=1024
            )
        except SandboxError as err:
            expected = err
        else:
            await sandbox.destroy()
            raise AssertionError("expected the Dev Server to reject sandboxes")

        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()

        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == {
            "action": "create",
            # The step failed without retries, so no attempt was used.
            "attempt": 0,
            "code": expected.code,
            "retryable": False,
            "status": expected.status,
        }
        assert expected.retryable is False
        assert expected.status is not None and 400 <= expected.status < 500

    return base.Case(
        fn=fn_sync if is_sync else fn_async,
        run_test=run_test,
        name=test_name,
    )
