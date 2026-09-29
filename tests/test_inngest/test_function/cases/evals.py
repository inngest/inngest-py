from __future__ import annotations

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

    @client.create_function(
        fn_id=test_name, trigger=inngest.TriggerEvent(event=event_name)
    )
    def parent_sync(ctx: inngest.ContextSync) -> dict[str, object]:
        state.run_id = ctx.run_id
        selected = ctx.group.experiment(
            "model",
            variants={
                "control": lambda: ctx.step.run("baseline", lambda: 7),
                "variant": lambda: ctx.step.run("candidate", lambda: 8),
            },
            select=experiment.bucket("alice"),
        )
        ctx.step.run(
            "score-turns",
            lambda: client.score_sync(
                run_id=ctx.run_id, name="turns", value=selected.result
            ),
        )
        return selected.experiment_ref.model_dump()

    @client.create_function(
        fn_id=test_name, trigger=inngest.TriggerEvent(event=event_name)
    )
    async def parent_async(ctx: inngest.Context) -> dict[str, object]:
        state.run_id = ctx.run_id

        async def baseline() -> int:
            return 7

        async def candidate() -> int:
            return 8

        selected = await ctx.group.experiment(
            "model",
            variants={
                "control": lambda: ctx.step.run("baseline", baseline),
                "variant": lambda: ctx.step.run("candidate", candidate),
            },
            select=experiment.bucket("alice"),
        )
        await ctx.step.run(
            "score-turns",
            lambda: client.score(
                run_id=ctx.run_id, name="turns", value=selected.result
            ),
        )
        return selected.experiment_ref.model_dump()

    trigger = inngest.TriggerEvent(event=f"{event_name}/approved")

    @client.create_function(fn_id=f"{test_name}-scorer", trigger=trigger)
    def scorer_sync(ctx: inngest.ContextSync) -> None:
        ref = experiment.ExperimentRef.model_validate(
            ctx.event.data["experiment"]
        )
        ctx.step.run(
            "approve",
            lambda: client.score_experiment_sync(
                experiment=ref,
                run_id=str(ctx.event.data["run_id"]),
                name="approved",
                value=True,
            ),
        )

    @client.create_function(fn_id=f"{test_name}-scorer", trigger=trigger)
    async def scorer_async(ctx: inngest.Context) -> None:
        ref = experiment.ExperimentRef.model_validate(
            ctx.event.data["experiment"]
        )
        await ctx.step.run(
            "approve",
            lambda: client.score_experiment(
                experiment=ref,
                run_id=str(ctx.event.data["run_id"]),
                name="approved",
                value=True,
            ),
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id, test_core.helper.RunStatus.COMPLETED
        )
        assert run.output is not None

        event_ids = self.client.send_sync(
            inngest.Event(
                name=f"{event_name}/approved",
                data={
                    "run_id": run_id,
                    "experiment": json.loads(run.output),
                },
            )
        )
        scorer_ids = await test_core.helper.client.get_run_ids_from_event_id(
            event_ids[0], run_count=1
        )
        await test_core.helper.client.wait_for_run_status(
            scorer_ids[0], test_core.helper.RunStatus.COMPLETED
        )

        async def metadata_visible() -> None:
            gql = test_core.gql.Client(f"{dev_server.server.origin}/v0/gql")
            result = await gql.query(
                test_core.gql.Query(
                    """query($id: String!) {
                        run(runID: $id) {
                            trace {
                                metadata { kind scope values }
                                childrenSpans {
                                    name metadata { kind scope values }
                                }
                            }
                        }
                    }""",
                    {"id": run_id},
                )
            )
            assert isinstance(result, test_core.gql.Response), result
            data = typing.cast(dict[str, typing.Any], result.data)
            metadata = {
                item["kind"]: item for item in data["run"]["trace"]["metadata"]
            }
            assert metadata["inngest.score"]["values"] == {
                "turns": {"value": 7},
                "approved": {"value": True},
            }
            assert metadata["inngest.experiment"]["scope"] == "run"
            assert metadata["inngest.experiment"]["values"] == {
                "name": "model",
                "variant": "control",
            }
            # Verify attribution emitted by execution, independently of the
            # run attribution written later by score_experiment().
            step_experiments = {
                span["name"]: item
                for span in data["run"]["trace"]["childrenSpans"]
                for item in typing.cast(
                    list[dict[str, typing.Any]], span["metadata"] or []
                )
                if item["kind"] == "inngest.experiment"
            }
            for name in ("model", "baseline"):
                assert step_experiments[name]["scope"] == "step"
                values = step_experiments[name]["values"]
                assert values["name"] == "model"
                assert values["variant"] == "control"
                assert values["selection_strategy"] == "bucket"
            assert step_experiments["model"]["values"][
                "available_variants"
            ] == ["control", "variant"]

        await base.wait_for(metadata_visible)

    return base.Case(
        fn=[parent_sync, scorer_sync]
        if is_sync
        else [parent_async, scorer_async],
        name=test_name,
        run_test=run_test,
    )
