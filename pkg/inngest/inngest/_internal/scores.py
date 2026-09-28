from __future__ import annotations

import math
import re
import typing
import urllib.parse

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib

ScoreValue: typing.TypeAlias = bool | int | float


def validate_score(
    name: object, value: object, run_id: object, step_id: object
) -> None:
    """Reject scores that the metadata backend cannot aggregate."""
    for field, identifier in (("run_id", run_id), ("step_id", step_id)):
        if (field == "run_id" or identifier is not None) and (
            not isinstance(identifier, str) or not identifier.strip()
        ):
            raise ValueError(f"{field} must be a non-empty string")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Score name must be a non-empty string")
    if re.search(r"[\x00-\x1f\x7f']", name) or len(name.encode("utf-8")) > 128:
        raise ValueError(
            "Score names must be at most 128 UTF-8 bytes and contain no control characters or single quotes"
        )
    if not isinstance(value, (bool, int, float)) or (
        isinstance(value, float) and not math.isfinite(value)
    ):
        raise ValueError("Score value must be a finite number or boolean")


def prepare_update(
    client: client_lib.Inngest,
    *,
    kind: str,
    values: dict[str, object],
    run_id: str,
    step_id: str | None,
) -> tuple[str, dict[str, object]]:
    """Build an explicitly targeted authenticated metadata API update."""
    target: dict[str, object] = {"run_id": run_id}
    if step_id is not None:
        target["step_id"] = step_id
    path = f"/v1/runs/{urllib.parse.quote(run_id, safe='')}/metadata"
    return urllib.parse.urljoin(client.api_origin, path), {
        "target": target,
        "metadata": [{"kind": kind, "op": "merge", "values": values}],
    }


async def write(
    client: client_lib.Inngest,
    *,
    kind: str,
    values: dict[str, object],
    run_id: str,
    step_id: str | None,
) -> None:
    """Write metadata via the authenticated API."""
    request = prepare_update(
        client, kind=kind, values=values, run_id=run_id, step_id=step_id
    )
    response = await client._http_client.post(*request)
    if isinstance(response, Exception):
        raise response


def write_sync(
    client: client_lib.Inngest,
    *,
    kind: str,
    values: dict[str, object],
    run_id: str,
    step_id: str | None,
) -> None:
    """Synchronous metadata writer."""
    request = prepare_update(
        client, kind=kind, values=values, run_id=run_id, step_id=step_id
    )
    response = client._http_client.post_sync(*request)
    if isinstance(response, Exception):
        raise response
