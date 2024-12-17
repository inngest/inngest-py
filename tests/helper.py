from __future__ import annotations

import enum
import json
import time
import typing

import pydantic

import inngest
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


class _Client:
    def __init__(self) -> None:
        self._gql = gql.Client(f"{dev_server.server.origin}/v0/gql")

    def _get_history(
        self,
        run_id: str,
    ) -> list[object]:
        query = """
        query GetHistory($run_id: ID!) {
            functionRun(query: { functionRunId: $run_id }) {
                history {
                    id
                    stepName
                }
            }
        }
        """
        res = self._gql.query(gql.Query(query, {"run_id": run_id}))
        if isinstance(res, gql.Error):
            raise Exception(res.message)

        run = res.data["functionRun"]
        if not isinstance(run, dict):
            raise Exception("unexpected response")

        history = run["history"]
        if not isinstance(history, list):
            raise Exception("unexpected response")

        return history

    def get_step_output(
        self,
        *,
        run_id: str,
        step_id: str,
    ) -> str:
        history = self._get_history(run_id)
        if not isinstance(history, list):
            raise Exception("unexpected response")

        history_item_id: typing.Optional[str] = None
        for step in history:
            if not isinstance(step, dict):
                raise Exception("unexpected response")
            if step["stepName"] == step_id:
                history_item_id = step["id"]
                break
        if not history_item_id:
            raise Exception(f'step "{step_id}" not found in history')

        query = """
        query GetHistory($history_item_id: ULID!, $run_id: ID!) {
            functionRun(query: { functionRunId: $run_id }) {
                historyItemOutput(id: $history_item_id)
            }
        }
        """
        res = self._gql.query(
            gql.Query(
                query,
                {
                    "history_item_id": history_item_id,
                    "run_id": run_id,
                },
            )
        )
        if isinstance(res, gql.Error):
            raise Exception(res.message)

        run = res.data["functionRun"]
        if not isinstance(run, dict):
            raise Exception("unexpected response")

        output = run["historyItemOutput"]
        if not isinstance(output, str):
            raise Exception("unexpected response")
        return output

    def get_run_ids_from_event_id(
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
        while True:
            res = self._gql.query(gql.Query(query, {"event_id": event_id}))
            if isinstance(res, gql.Response):
                event = res.data.get("event")
                if not isinstance(event, dict):
                    raise Exception("unexpected response")
                runs = event.get("functionRuns")
                if not isinstance(runs, list):
                    raise Exception("unexpected response")
                if len(runs) == run_count:
                    return [run["id"] for run in runs]

            if time.time() - start > timeout:
                raise Exception("timed out waiting for run status")

            time.sleep(0.2)

    def wait_for_run_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        timeout: int = 5,
    ) -> _Run:
        query = """
        query GetRun($run_id: ID!) {
            functionRun(query: { functionRunId: $run_id }) {
                event {
                    raw
                }
                id
                output
                status
            }
        }
        """

        start = time.time()
        while True:
            res = self._gql.query(gql.Query(query, {"run_id": run_id}))
            if isinstance(res, gql.Response):
                run = res.data.get("functionRun")
                if not isinstance(run, dict):
                    raise Exception("unexpected response")
                if run["status"] == status.value:
                    run["event"] = json.loads(run["event"]["raw"])
                    return _Run.model_validate(run)

                if any(run["status"] == s.value for s in ended_statuses):
                    # Fail early if the run ended with a different status
                    raise Exception(
                        f"run ended with a different status: {run['status']}"
                    )

            if time.time() - start > timeout:
                raise Exception(
                    "timed out waiting for run status, actual status is"
                )

            time.sleep(0.2)


class _Run(types.BaseModel):
    event: inngest.Event
    id: str
    output: typing.Optional[str]
    status: RunStatus

    @pydantic.field_validator("status", mode="before")
    @classmethod
    def convert_status(cls, value: str) -> RunStatus:
        if isinstance(value, str):
            return RunStatus(value)
        raise ValueError("invalid status")


client = _Client()
