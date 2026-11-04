"""
Two parallel tool calls in one AIMessage, then a final answer
"""

import inngest
from inngest._internal import server_lib
from langchain_core.messages import AIMessage

from . import base


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    return base.agent_case(
        client,
        framework,
        is_sync,
        test_name=base.create_test_name(__file__),
        script=[
            base.tool_turn(
                base.call("weather", "call_1", city="Paris"),
                base.call("local_time", "call_2", city="Paris"),
            ),
            AIMessage(content="It's sunny in Paris at noon."),
        ],
        steps=[
            "weather/model-0",
            "weather/tool-call_1",
            "weather/tool-call_2",
            "weather/model-1",
        ],
        tools=["weather", "local_time"],
    )
