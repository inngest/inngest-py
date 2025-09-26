from __future__ import annotations

import typing

from inngest._internal import types

from .event import Event


class ServerRequest(types.BaseModel):
    ctx: ServerRequestCtx
    event: Event
    events: typing.Optional[list[Event]] = None
    steps: dict[str, object]
    use_api: bool


class ServerRequestCtx(types.BaseModel):
    attempt: int
    disable_immediate_execution: bool
    max_attempts: int | None = None
    run_id: str
    stack: ServerRequestCtxStack


class ServerRequestCtxStack(types.BaseModel):
    stack: typing.Optional[list[str]] = None
