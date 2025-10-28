import functools

import inngest
import inngest.experimental

from .client import inngest_client


@inngest_client.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
def hello(ctx: inngest.ContextSync) -> str:
    return "Hello world!"


@inngest.experimental.step("get-message")
def get_message(*, name: str) -> str:
    return f"Hello {name}!"


@inngest_client.create_function(
    fn_id="fn-1",
    trigger=inngest.TriggerEvent(event="event-1"),
)
def fn_1(ctx: inngest.ContextSync) -> str:
    msg = get_message(name="Alice")
    return msg


@inngest_client.create_function(
    fn_id="fn-2",
    trigger=inngest.TriggerEvent(event="event-2"),
)
def fn_2(ctx: inngest.ContextSync) -> str:
    msg = get_message(name="Alice")
    return msg
