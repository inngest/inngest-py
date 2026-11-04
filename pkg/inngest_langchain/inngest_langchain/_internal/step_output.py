"""
What model and tool steps store, and how it becomes LangChain objects again.

The format is private but long-lived once released: runs in flight replay it
after a deploy.
"""

from __future__ import annotations

import dataclasses
import json
import typing

import inngest
import pydantic
import pydantic_core
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain.agents.structured_output import (
    ProviderStrategy,
    ToolStrategy,
    _SchemaSpec,
)
from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.types import Command

ToolResult: typing.TypeAlias = ToolMessage | Command[typing.Any]

_T = typing.TypeVar("_T")


class _Structured(pydantic.BaseModel):
    """
    A parsed structured response. `variant` names the schema it was parsed
    with (None for an untitled JSON schema dict); `value` is its JSON, by field
    name.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    variant: str | None
    value: typing.Any


class _ModelStep(pydantic.BaseModel):
    """A model call's output messages and any parsed structured response."""

    model_config = pydantic.ConfigDict(extra="forbid")

    v: typing.Literal[1] = 1
    messages: list[AnyMessage]
    structured: _Structured | None = None


class _ToolMessageStep(pydantic.BaseModel):
    """A tool call that returned a `ToolMessage`."""

    model_config = pydantic.ConfigDict(extra="forbid")

    v: typing.Literal[1] = 1
    kind: typing.Literal["message"] = "message"
    message: ToolMessage


class _ToolUpdateStep(pydantic.BaseModel):
    """
    A tool call that returned `Command(update=...)`. `messages` stay messages;
    every other key comes back as plain JSON values.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    v: typing.Literal[1] = 1
    kind: typing.Literal["update"] = "update"
    messages: list[AnyMessage] | None = None
    state: dict[str, typing.Any]


_ToolStep = typing.Annotated[
    _ToolMessageStep | _ToolUpdateStep,
    pydantic.Field(discriminator="kind"),
]

_model_step = pydantic.TypeAdapter(_ModelStep)
_tool_step: pydantic.TypeAdapter[_ToolMessageStep | _ToolUpdateStep] = (
    pydantic.TypeAdapter(_ToolStep)
)


def record_model(
    request: ModelRequest[typing.Any], response: ModelResponse[typing.Any]
) -> dict[str, object]:
    """The JSON a model step stores."""

    structured = None
    if response.structured_response is not None:
        structured = _record_structured(request, response)
    return _to_json(
        "the model returned a response that",
        lambda: _ModelStep(
            messages=typing.cast(list[AnyMessage], response.result),
            structured=structured,
        ),
    )


def replay_model(
    request: ModelRequest[typing.Any], step_id: str, data: object
) -> ModelResponse[typing.Any]:
    step = _validate(_model_step, step_id, data)
    structured = None
    if step.structured is not None:
        structured = _replay_structured(request, step_id, step.structured)
    return ModelResponse(
        result=list(step.messages), structured_response=structured
    )


def record_tool(name: str, result: object) -> dict[str, object]:
    """The JSON a tool step stores."""

    what = f"tool {name} returned a {type(result).__name__} that"
    if isinstance(result, ToolMessage):
        return _to_json(what, lambda: _ToolMessageStep(message=result))

    state = _plain_update(name, result)
    messages = state.pop("messages", None)
    return _to_json(
        what, lambda: _ToolUpdateStep(messages=messages, state=state)
    )


def replay_tool(step_id: str, data: object) -> ToolResult:
    step = _validate(_tool_step, step_id, data)
    if isinstance(step, _ToolMessageStep):
        return step.message

    update = dict(step.state)
    if step.messages is not None:
        update["messages"] = step.messages
    return Command(update=update)


def _specs(request: ModelRequest[typing.Any]) -> list[_SchemaSpec[typing.Any]]:
    """Every schema LangChain may have parsed the response with."""

    fmt = request.response_format
    if isinstance(fmt, ProviderStrategy):
        return [fmt.schema_spec]
    if isinstance(fmt, ToolStrategy):
        return fmt.schema_specs
    if fmt is None:
        return []
    # An AutoStrategy resolves to one of the strategies above, and both name
    # each variant the same way.
    return ToolStrategy(fmt.schema).schema_specs


def _variant(spec: _SchemaSpec[typing.Any]) -> str | None:
    # An untitled JSON schema gets a random name in every process.
    if isinstance(spec.schema, dict) and "title" not in spec.schema:
        return None
    return spec.name


def _record_structured(
    request: ModelRequest[typing.Any], response: ModelResponse[typing.Any]
) -> _Structured:
    specs = _specs(request)
    if len(specs) > 1:
        # ToolStrategy answers its structured output call with a ToolMessage
        # named after the variant it parsed.
        names = {m.name for m in response.result if isinstance(m, ToolMessage)}
        specs = [s for s in specs if s.name in names]
    if len(specs) != 1:
        raise inngest.NonRetriableError(
            "can't tell which response_format schema produced the structured "
            "response, so it can't be recorded"
        )
    spec = specs[0]
    value = response.structured_response
    if isinstance(spec.schema, dict):
        return _Structured(variant=_variant(spec), value=value)

    adapter = pydantic.TypeAdapter[typing.Any](spec.schema)
    try:
        raw = adapter.dump_json(value, by_alias=False)
        replayed = adapter.validate_json(raw, by_alias=False, by_name=True)
    except (ValueError, pydantic_core.PydanticSerializationError) as exc:
        raise inngest.NonRetriableError(
            f"the structured response cannot be recorded as JSON: {exc}"
        ) from exc
    if not _same(value, replayed):
        raise inngest.NonRetriableError(
            f"the structured response {value!r} would replay as {replayed!r}; "
            "check its validators, excluded fields and Any-typed values"
        )
    return _Structured(variant=_variant(spec), value=json.loads(raw))


def _replay_structured(
    request: ModelRequest[typing.Any], step_id: str, recorded: _Structured
) -> object:
    spec = next(
        (s for s in _specs(request) if _variant(s) == recorded.variant), None
    )
    if spec is None:
        raise inngest.NonRetriableError(
            f"step {step_id} recorded a structured response for schema "
            f"{recorded.variant!r}, which the agent's response_format no "
            "longer has"
        )
    if isinstance(spec.schema, dict):
        return recorded.value
    try:
        return pydantic.TypeAdapter[typing.Any](spec.schema).validate_json(
            json.dumps(recorded.value), by_alias=False, by_name=True
        )
    except ValueError as exc:
        raise inngest.NonRetriableError(
            f"step {step_id} recorded a structured response that schema "
            f"{recorded.variant!r} no longer accepts: {exc}"
        ) from exc


def _same(a: object, b: object) -> bool:
    """`==` that also requires the same types all the way down."""

    if type(a) is not type(b):
        return False
    if isinstance(a, pydantic.BaseModel) and isinstance(b, pydantic.BaseModel):
        return _same(vars(a), vars(b)) and _same(
            a.__pydantic_extra__, b.__pydantic_extra__
        )
    if dataclasses.is_dataclass(a):
        names = [f.name for f in dataclasses.fields(a)]
        return _same(
            [getattr(a, n) for n in names], [getattr(b, n) for n in names]
        )
    if isinstance(a, (set, frozenset)) and isinstance(b, (set, frozenset)):
        return _same(dict.fromkeys(a), dict.fromkeys(b))
    if isinstance(a, dict) and isinstance(b, dict):
        b_keys = {k: k for k in b}
        return len(a) == len(b) and all(
            k in b_keys and _same(k, b_keys[k]) and _same(v, b[k])
            for k, v in a.items()
        )
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(map(_same, a, b))
    return a == b


def _plain_update(name: str, result: object) -> dict[str, typing.Any]:
    """The update of a routing-free `Command(update={...})`."""

    if not isinstance(result, Command):
        raise inngest.NonRetriableError(
            f"tool {name} returned {type(result).__name__}; "
            "only ToolMessage or Command results can be recorded as a step"
        )
    if result.graph is not None or result.goto or result.resume is not None:
        raise inngest.NonRetriableError(
            f"tool {name} returned a Command with routing (graph, goto or "
            "resume); only Command(update={...}) can be recorded as a step"
        )
    if not isinstance(result.update, dict):
        raise inngest.NonRetriableError(
            f"tool {name} returned "
            f"Command(update={type(result.update).__name__}); "
            "only a dict update can be recorded as a step"
        )
    return dict(result.update)


def _to_json(
    what: str,
    build: typing.Callable[[], pydantic.BaseModel],
) -> dict[str, object]:
    """
    Build a step's output and dump it to JSON. A value that can't become JSON
    fails the same way on every attempt, so it isn't retried. `ValueError`
    covers `ValidationError` and `UnicodeDecodeError`.
    """

    try:
        return build().model_dump(mode="json")
    except (ValueError, pydantic_core.PydanticSerializationError) as exc:
        raise inngest.NonRetriableError(
            f"{what} cannot be recorded as JSON: {exc}"
        ) from exc


def _validate(
    adapter: pydantic.TypeAdapter[_T],
    step_id: str,
    data: object,
) -> _T:
    try:
        return adapter.validate_python(data)
    except pydantic.ValidationError as exc:
        raise inngest.NonRetriableError(
            f"step {step_id} stored output this version of "
            f"inngest_langchain can't read: {exc}"
        ) from exc
