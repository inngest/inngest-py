from .function import Function
from .types import FunctionHandler, TriggerCron, TriggerEvent


class Inngest:
    def __init__(
        self,
        *,
        id: str,  # pylint: disable=redefined-builtin
    ) -> None:
        self.id = id

    def create_function(
        self,
        *,
        id: str,  # pylint: disable=redefined-builtin
        trigger: TriggerCron | TriggerEvent,
        handler: FunctionHandler,
    ) -> Function:
        return Function(
            id=id,
            trigger=trigger,
            handler=handler,
        )
