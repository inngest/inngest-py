import time
from enum import Enum

from inngest._internal.result import is_ok

from . import dev_server, gql


class RunStatus(Enum):
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"


class _Client:
    def __init__(self) -> None:
        self._gql = gql.Client(f"http://localhost:{dev_server.PORT}/v0/gql")

    def wait_for_run_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        timeout: int = 5,
    ) -> None:
        query = """
        query GetRun($run_id: ID!) {
            functionRun(query: { functionRunId: $run_id }) {
                id
                status
            }
        }
        """

        start = time.time()
        while True:
            res = self._gql.query(gql.Query(query, {"run_id": run_id}))
            if is_ok(res):
                run = res.value.data.get("functionRun")
                if not isinstance(run, dict):
                    raise Exception("unexpected response")
                if run["status"] == status.value:
                    return

            if time.time() - start > timeout:
                raise Exception("timed out waiting for run status")

            time.sleep(0.2)


client = _Client()
