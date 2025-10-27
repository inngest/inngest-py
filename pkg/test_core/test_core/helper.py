from __future__ import annotations

import asyncio
import enum
import json
import time

import inngest
import pydantic
from inngest._internal import types
from inngest.experimental import dev_server

from . import gql


class RunStatus(enum.Enum):
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"


ended_statuses = set(
    [
        RunStatus.CANCELLED,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
    ]
)


class _Step(types.BaseModel):
    name: str
    output_id: str | None = pydantic.Field(alias="outputID")


class _Client:
    def __init__(self) -> None:
        self._gql = gql.Client(f"{dev_server.server.origin}/v0/gql")

    async def _get_steps(
        self,
        run_id: str,
    ) -> list[_Step]:
        query = """
        query GetHistory($run_id: String!) {
            run(runID: $run_id) {
                trace {
                    childrenSpans {
                        name
                        outputID
                    }
                }
            }
        }
        """
        res = await self._gql.query(gql.Query(query, {"run_id": run_id}))
        if isinstance(res, gql.Error):
            raise Exception(res.message)

        run = res.data["run"]
        if not isinstance(run, dict):
            raise Exception("unexpected response")

        trace = run["trace"]
        if not isinstance(trace, dict):
            raise Exception("unexpected response")

        children_spans = trace["childrenSpans"]
        if not isinstance(children_spans, list):
            raise Exception("unexpected response")

        return [_Step.model_validate(span) for span in children_spans]

    async def get_step_output(
        self,
        *,
        run_id: str,
        step_id: str,
        index=None: int | None,
    ) -> str:
        history = await self._get_steps(run_id)
        if not isinstance(history, list):
            raise Exception("unexpected response")

        expected = 1 if index is None else index + 1
        found = 0
        output_id: str | None = None
        for step in history:
            if step.name == step_id:
                found += 1
                if found == expected:
                    output_id = step.output_id
                    break
        if not output_id:
            if index is None:
                raise Exception(f'step "{step_id}" not found in history')
            else:
                raise Exception(f'step "{step_id}" index={index} not found in history')

        query = """
        query GetHistory($output_id: String!) {
            runTraceSpanOutputByID(outputID: $output_id) {
                data
                error {
                    message
                    name
                    stack
                }
            }
        }
        """
        res = await self._gql.query(gql.Query(query, {"output_id": output_id}))
        if isinstance(res, gql.Error):
            raise Exception(res.message)

        run = res.data["runTraceSpanOutputByID"]
        if not isinstance(run, dict):
            raise Exception("unexpected response")

        # Hacky stuff to maintain backwards compatibility with test code
        if run["error"] is None:
            del run["error"]
        if run["data"] is not None:
            run["data"] = json.loads(run["data"])

        return json.dumps(run)

    async def get_run_ids_from_event_id(
        self,
        event_id: str,
        *,
        run_count: int,
        timeout: int = 5,
    ) -> list[str]:
        query = """
        query GetRunFromEventID($event_id: ID!) {
            event(query: {eventId: $event_id}) {
                functionRuns {
                    id
                }
            }
        }
        """

        start = time.time()
        attempts = 0
        while True:
            if attempts > 0:
                await asyncio.sleep(0.2)
            attempts += 1

            res = await self._gql.query(
                gql.Query(query, {"event_id": event_id})
            )
            if isinstance(res, gql.Response):
                event = res.data.get("event")
                if not isinstance(event, dict):
                    raise Exception("unexpected response")
                runs = event.get("functionRuns") or []
                if not isinstance(runs, list):
                    raise Exception("unexpected response")
                if len(runs) == run_count:
                    return [run["id"] for run in runs]

            if time.time() - start > timeout:
                raise Exception("timed out waiting for run status")

    async def wait_for_run_status(
        self,
        run_id: str,
        expected_status: RunStatus,
        *,
        timeout: int = 20,
    ) -> _Run:
        query = """
        query GetRun($run_id: String!) {
            run(runID: $run_id) {
                output
                status
            }
            runTrigger(runID: $run_id) {
                payloads
            }
        }
        """

        start = time.time()
        actual_status: str | None = None
        while True:
            res = await self._gql.query(gql.Query(query, {"run_id": run_id}))
            if isinstance(res, gql.Response):
                run = res.data.get("run")
                if not isinstance(run, dict):
                    raise Exception("unexpected response")
                actual_status = run["status"]

                run_trigger = res.data.get("runTrigger")
                if not isinstance(run_trigger, dict):
                    raise Exception("unexpected response")
                payloads = run_trigger.get("payloads")
                if not isinstance(payloads, list):
                    raise Exception("unexpected response")
                event = inngest.Event.model_validate_json(payloads[0])

                if actual_status == expected_status.value:
                    return _Run(
                        event=event,
                        id=run_id,
                        output=run["output"],
                        status=RunStatus(actual_status),
                    )

                if any(actual_status == s.value for s in ended_statuses):
                    # Fail early if the run ended with a different status
                    raise Exception(
                        f"run ended with a different status: {actual_status}"
                    )

            if time.time() - start > timeout:
                msg = f"timed out waiting for run {run_id} status: no status available"
                if actual_status is not None:
                    msg = f"timed out waiting for run {run_id} status: actual status is {actual_status}"
                raise Exception(msg)

            await asyncio.sleep(0.2)


class _Run(types.BaseModel):
    event: inngest.Event
    id: str
    output: str | None
    status: RunStatus


client = _Client()
