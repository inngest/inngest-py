"""
Defers must not replay a failed parent or hide an invalid return value.

Only children accepted before the failure run. Buffered children are dropped,
so preserving the parent's failure does not require an extra execution.
"""

import asyncio

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import create_defer

from . import base


def create(
    client: inngest.Inngest, framework: server_lib.Framework, is_sync: bool
) -> base.Case:
    name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, name)
    cases = [
        ("error", False, False),
        ("error-after-step", True, False),
        ("invalid-output", False, True),
        ("invalid-output-after-step", True, True),
    ]
    parents = {label: base.BaseState() for label, _, _ in cases}
    children = {label: base.BaseState() for label, _, _ in cases}
    failures = dict.fromkeys(parents, 0)
    received: dict[str, list[str]] = {label: [] for label in parents}

    def receive(ctx: inngest.Context | inngest.ContextSync) -> None:
        label = str(ctx.event.data["case"])
        children[label].run_id = ctx.run_id
        received[label].append(str(ctx.event.data["child"]))
        assert ctx.parents[0].run_id == parents[label].run_id

    target = create_defer(client, fn_id=f"{name}-child", retries=0)(
        receive if is_sync else base.asyncify(receive)
    )

    def prepare(ctx: inngest.Context | inngest.ContextSync) -> None:
        label = str(ctx.event.data["case"])
        parents[label].run_id = ctx.run_id
        if ctx.event.data["checkpoint"]:
            ctx.defer(
                "accepted",
                function=target,
                data={"case": label, "child": "accepted"},
            )

    def fail(ctx: inngest.Context | inngest.ContextSync) -> object:
        label = str(ctx.event.data["case"])
        # Count after the checkpoint: ordinary step replay is expected, but
        # repeating the parent's failure (and its side effects) is not.
        failures[label] += 1
        ctx.defer(
            "buffered",
            function=target,
            data={"case": label, "child": "buffered"},
        )
        if ctx.event.data["unserializable"]:
            return object()
        raise inngest.NonRetriableError("intentional parent failure")

    def sync(ctx: inngest.ContextSync) -> object:
        prepare(ctx)
        if ctx.event.data["checkpoint"]:
            ctx.step.run("checkpoint", lambda: None)
        return fail(ctx)

    async def async_fn(ctx: inngest.Context) -> object:
        prepare(ctx)
        if ctx.event.data["checkpoint"]:

            async def checkpoint() -> None:
                pass

            await ctx.step.run("checkpoint", checkpoint)
        return fail(ctx)

    parent = client.create_function(
        fn_id=name, retries=0, trigger=inngest.TriggerEvent(event=event_name)
    )(sync if is_sync else async_fn)

    async def run_test(self: base.TestClass) -> None:
        for label, checkpoint, unserializable in cases:
            with self.subTest(case=label):
                self.client.send_sync(
                    inngest.Event(
                        name=event_name,
                        data={
                            "case": label,
                            "checkpoint": checkpoint,
                            "unserializable": unserializable,
                        },
                    )
                )
                parent_id = await parents[label].wait_for_run_id()
                await test_core.helper.client.wait_for_run_status(
                    parent_id, test_core.helper.RunStatus.FAILED
                )
                if checkpoint:
                    child_id = await children[label].wait_for_run_id()
                    await test_core.helper.client.wait_for_run_status(
                        child_id, test_core.helper.RunStatus.COMPLETED
                    )
                # Allow unexpected child deliveries or parent replays to appear.
                await asyncio.sleep(1)
                assert failures[label] == 1
                assert received[label] == (["accepted"] if checkpoint else [])

    return base.Case(fn=[parent, target], name=name, run_test=run_test)
