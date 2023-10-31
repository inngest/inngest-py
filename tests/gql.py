from __future__ import annotations

import httpx
import pydantic

from inngest._internal.result import Err, Ok, Result


class Client:
    def __init__(self, endpoint: str):
        self._endpoint = endpoint

    def query(self, query: Query) -> Result[_Response, _Error]:
        http_res = httpx.post(
            self._endpoint,
            json=query.payload(),
            timeout=30,
        )
        if http_res.status_code != 200:
            return Err(
                _Error(
                    message=f"API call failed with status code {http_res.status_code}"
                )
            )

        gql_res: _Response
        try:
            gql_res = _Response.model_validate(http_res.json())
        except Exception as e:
            return Err(_Error(message=f"failed to parse response as JSON: {e}"))

        if gql_res.errors is not None:
            return Err(_Error(message="GraphQL error", response=gql_res))

        return Ok(gql_res)


class Query:
    def __init__(
        self,
        query: str,
        variables: dict[str, object] | None = None,
    ):
        self._query = query
        self._variables = variables

    def payload(self) -> dict[str, object]:
        return {
            "query": self._query,
            "variables": self._variables,
        }


class _Response(pydantic.BaseModel):
    data: dict[str, object]
    errors: list[dict[str, object]] | None = None


class _Error(pydantic.BaseModel):
    response: _Response | None = None
    message: str
