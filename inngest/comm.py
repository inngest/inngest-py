from dataclasses import dataclass
import http.client
import json
from typing import TypeVar

from .client import Inngest
from .const import language, version
from .function import Function
from .types import (
    ActionError,
    ActionResponse,
    FunctionCall,
    FunctionConfig,
    RegisterRequest,
)


T = TypeVar("T")


@dataclass
class Response:
    body: str
    headers: dict[str, str]
    status_code: int


class InngestCommHandler:
    def __init__(
        self,
        *,
        client: Inngest,
        framework: str,
        functions: list[Function],
    ) -> None:
        self._client = client
        self._fns: dict[str, Function] = {fn.get_id(): fn for fn in functions}
        self._framework = framework

    def call_function(
        self,
        *,
        call: FunctionCall,
        fn_id: str,
    ) -> Response:
        if fn_id not in self._fns:
            raise Exception(f"function {fn_id} not found")

        body: str
        status_code: int
        headers: dict[str, str] = {}
        res = self._fns[fn_id].call(call)
        if isinstance(res, list):
            out: list[dict[str, object]] = []
            for item in res:
                if not isinstance(item, ActionResponse):
                    raise Exception("expected ActionResponse")

                out.append(item.to_dict())

            body = json.dumps(remove_none_deep(out))
            status_code = 206
        elif isinstance(res, ActionError):
            body = json.dumps(remove_none_deep(res.to_dict()))
            status_code = 500

            if res.is_retriable is False:
                headers["x-inngest-no-retry"] = "true"
        else:
            body = res
            status_code = 200

        return Response(
            body=body,
            headers=headers,
            status_code=status_code,
        )

    def _get_function_configs(self) -> list[FunctionConfig]:
        return [fn.get_config() for fn in self._fns.values()]

    def handle_action(self) -> None:
        return None

    def register(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1:8288")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"inngest-{language}:v{version}",
            "x-inngest-sdk": f"inngest-{language}:v{version}",
            "x-inngest-framework": self._framework,
            "Server-Timing": "handler",
            "Authorization": "Bearer ",
        }

        body = json.dumps(
            remove_none_deep(
                RegisterRequest(
                    app_name=self._client.id,
                    framework=self._framework,
                    functions=self._get_function_configs(),
                    hash="094cd50f64aadfec073d184bedd7b7d077f919b3d5a19248bb9a68edbc66597c",
                    sdk=f"{language}:v{version}",
                    url="http://localhost:8000/api/inngest",
                    v="0.1",
                ).to_dict()
            )
        )

        conn.request(
            "POST",
            "/fn/register",
            body=body,
            headers=headers,
        )
        conn.getresponse()
        conn.close()


def remove_none_deep(obj: T) -> T:
    if isinstance(obj, dict):
        return {k: remove_none_deep(v) for k, v in obj.items() if v is not None}  # type: ignore
    elif isinstance(obj, list):
        return [remove_none_deep(v) for v in obj if v is not None]  # type: ignore
    else:
        return obj
