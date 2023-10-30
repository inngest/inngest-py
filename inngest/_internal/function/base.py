from __future__ import annotations

import dataclasses
import typing

import pydantic

from inngest._internal import const, errors, function_config, types

FunctionHandlerT = typing.TypeVar("FunctionHandlerT")


class FunctionBase(typing.Generic[FunctionHandlerT]):
    _handler: FunctionHandlerT
    _on_failure_fn_id: str | None = None
    _opts: FunctionOptsBase[FunctionHandlerT]
    _trigger: function_config.TriggerCron | function_config.TriggerEvent

    @property
    def id(self) -> str:
        return self._opts.id

    @property
    def on_failure_fn_id(self) -> str | None:
        return self._on_failure_fn_id

    def get_config(self, app_url: str) -> _Config:
        fn_id = self._opts.id

        name = fn_id
        if self._opts.name is not None:
            name = self._opts.name

        if self._opts.retries is not None:
            retries = function_config.Retries(attempts=self._opts.retries)
        else:
            retries = None

        main = function_config.FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
            debounce=self._opts.debounce,
            id=fn_id,
            name=name,
            rate_limit=self._opts.rate_limit,
            steps={
                const.ROOT_STEP_ID: function_config.Step(
                    id=const.ROOT_STEP_ID,
                    name=const.ROOT_STEP_ID,
                    retries=retries,
                    runtime=function_config.Runtime(
                        type="http",
                        url=f"{app_url}?fnId={fn_id}&stepId={const.ROOT_STEP_ID}",
                    ),
                ),
            },
            throttle=self._opts.throttle,
            triggers=[self._trigger],
        )

        on_failure = None
        if self.on_failure_fn_id is not None:
            on_failure = function_config.FunctionConfig(
                id=self.on_failure_fn_id,
                name=f"{name} (on_failure handler)",
                steps={
                    const.ROOT_STEP_ID: function_config.Step(
                        id=const.ROOT_STEP_ID,
                        name=const.ROOT_STEP_ID,
                        retries=function_config.Retries(attempts=0),
                        runtime=function_config.Runtime(
                            type="http",
                            url=f"{app_url}?fnId={self.on_failure_fn_id}&stepId={const.ROOT_STEP_ID}",
                        ),
                    )
                },
                triggers=[
                    function_config.TriggerEvent(
                        event=const.InternalEvents.FUNCTION_FAILED.value,
                        expression=f"event.data.function_id == '{self.id}'",
                    )
                ],
            )

        return _Config(main=main, on_failure=on_failure)

    def get_id(self) -> str:
        return self._opts.id


class FunctionOptsBase(types.BaseModel, typing.Generic[FunctionHandlerT]):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    batch_events: function_config.Batch | None = None
    cancel: list[function_config.Cancel] | None = None
    debounce: function_config.Debounce | None = None
    id: str
    name: str | None = None
    on_failure: FunctionHandlerT | None = None
    rate_limit: function_config.RateLimit | None = None
    retries: int | None = None
    throttle: function_config.Throttle | None = None

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.InvalidConfig.from_validation_error(err)


@dataclasses.dataclass
class _Config:
    # The user-defined function
    main: function_config.FunctionConfig

    # The internal on_failure function
    on_failure: function_config.FunctionConfig | None
