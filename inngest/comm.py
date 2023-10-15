import http.client
import json

from .client import Inngest
from .const import language, version
from .function import Function
from .types import ActionResponse, Event, FunctionConfig, RegisterRequest


class InngestCommHandler:
    def __init__(
        self,
        *,
        client: Inngest,
        framework: str,
        functions: list[Function],
    ) -> None:
        self._client = client
        self._fns: dict[str, Function] = {fn.id: fn for fn in functions}
        self._framework = framework

    def call_function(
        self,
        *,
        id: str,  # pylint: disable=redefined-builtin
        event: Event,
    ) -> str:
        if id not in self._fns:
            raise Exception(f"function {id} not found")

        data = self._fns[id].handler(event=event)

        return json.dumps(data)

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
            RegisterRequest(
                appName=self._client.id,
                framework=self._framework,
                functions=self._get_function_configs(),
                hash="094cd50f64aadfec073d184bedd7b7d077f919b3d5a19248bb9a68edbc66597c",
                sdk=f"{language}:v{version}",
                url="http://localhost:8000/api/inngest",
                v="0.1",
            ).to_dict()
        )

        conn.request(
            "POST",
            "/fn/register",
            body=body,
            headers=headers,
        )
        conn.getresponse()
        conn.close()
