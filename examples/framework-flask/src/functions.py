import inngest

from .client import inngest_client


def _my_function(*, event: inngest.Event) -> str:
    print("called my_function")
    return "hi"


my_function = inngest_client.create_function(
    id="my-function",
    trigger=inngest.TriggerEvent(event="my-event"),
    handler=_my_function,
)


def _my_other_function(*, event: inngest.Event) -> int:
    print("called my_other_function")
    return 1


my_other_function = inngest_client.create_function(
    id="my-other-function",
    trigger=inngest.TriggerEvent(event="my-other-event"),
    handler=_my_other_function,
)

functions = [my_function, my_other_function]
