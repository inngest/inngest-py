from .types import (
    FunctionConfig,
    FunctionHandler,
    Runtime,
    Step,
    TriggerCron,
    TriggerEvent,
)


class Function:
    def __init__(
        self,
        *,
        id: str,  # pylint: disable=redefined-builtin
        trigger: TriggerCron | TriggerEvent,
        handler: FunctionHandler,
    ) -> None:
        self.id = id
        self.handler = handler
        self.trigger = trigger

    def get_config(self) -> FunctionConfig:
        return FunctionConfig(
            id=self.id,
            name=self.id,
            steps={
                "step": Step(
                    id="step",
                    name="step",
                    runtime=Runtime(
                        type="http",
                        url=f"http://localhost:8000/api/inngest?fnId={self.id}&stepId=step",
                    ),
                ),
            },
            triggers=[self.trigger],
        )
