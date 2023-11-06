from __future__ import annotations

import enum
import time

import pydantic

from inngest._internal import types

from . import dev_server, gql


class RunStatus(enum.Enum):
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"


class _Client:
    def __init__(self) -> None:
        self._gql = gql.Client(f"http://localhost:{dev_server.PORT}/v0/gql")

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
                    return _Run.model_validate(run)

            if time.time() - start > timeout:
                raise Exception("timed out waiting for run status")

            time.sleep(0.2)


class _Run(types.BaseModel):
    id: str
    output: str | None
    status: RunStatus

    @pydantic.field_validator("status", mode="before")
    @classmethod
    def convert_status(cls, value: str) -> RunStatus:
        if isinstance(value, str):
            return RunStatus(value)
        raise ValueError("invalid status")


client = _Client()
