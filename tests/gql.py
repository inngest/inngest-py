from __future__ import annotations

import typing

import httpx
import pydantic


class Client:
    def __init__(self, endpoint: str):
        self._endpoint = endpoint

    def query(self, query: Query) -> typing.Union[Response, Error]:
        http_res = httpx.post(
            self._endpoint,
            json=query.payload(),
            timeout=30,
        )
        if http_res.status_code != 200:
            return Error(
                message=f"API call failed with status code {http_res.status_code}"
            )

        gql_res: Response
        try:
            gql_res = Response.model_validate(http_res.json())
        except Exception as e:
            return Error(message=f"failed to parse response as JSON: {e}")

        if gql_res.errors is not None:
            return Error(message="GraphQL error", response=gql_res)

        return gql_res


class Query:
    def __init__(
        self,
        query: str,
        variables: typing.Optional[dict[str, object]] = None,
    ):
        self._query = query
        self._variables = variables

    def payload(self) -> dict[str, object]:
        return {
            "query": self._query,
            "variables": self._variables,
        }


class Response(pydantic.BaseModel):
    data: dict[str, object]
    errors: typing.Optional[list[dict[str, object]]] = None


class Error(pydantic.BaseModel):
    response: typing.Optional[Response] = None
    message: str
