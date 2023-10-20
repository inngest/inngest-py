from __future__ import annotations
from typing import Literal

from .types import BaseModel


class FunctionConfig(BaseModel):
    id: str
    name: str | None = None
    steps: dict[str, StepConfig]
    triggers: list[TriggerCron | TriggerEvent]


class Runtime(BaseModel):
    type: Literal["http"]
    url: str


class StepConfig(BaseModel):
    id: str
    name: str
    retries: StepConfigRetries | None = None
    runtime: Runtime


class StepConfigRetries(BaseModel):
    attempts: int


class TriggerCron(BaseModel):
    cron: str


class TriggerEvent(BaseModel):
    event: str
    expression: str | None = None
