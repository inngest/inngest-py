"""
The stored step format. Fixtures pin the JSON that runs in flight replay, so a
LangChain or pydantic upgrade that changes it fails here.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import json
import pathlib
import typing
import uuid

import inngest
import pydantic
import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain.agents.structured_output import (
    AutoStrategy,
    ProviderStrategy,
    ResponseFormat,
    ToolStrategy,
)
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command
from typing_extensions import TypedDict

from . import step_output
from .fakes_test import Counters, FakeRun, ScriptedModel, call, drive, tool_turn

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "steps"

_AI = AIMessage(
    id="msg_01XFDUDYJgAACzvnptvVoYEL",
    content=[
        {
            "type": "thinking",
            "thinking": "The user wants the weather in Paris. I should call "
            "the weather tool.",
            "signature": "EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds",
        },
        {"type": "text", "text": "Let me check the weather in Paris."},
        {
            "type": "tool_use",
            "id": "toolu_01A09q90qw90lq917835lq9",
            "name": "weather",
            "input": {"city": "Paris"},
        },
    ],
    tool_calls=[
        {
            "name": "weather",
            "args": {"city": "Paris"},
            "id": "toolu_01A09q90qw90lq917835lq9",
            "type": "tool_call",
        }
    ],
    response_metadata={
        "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
        "model": "claude-sonnet-4-5-20250929",
        "model_name": "claude-sonnet-4-5-20250929",
        "model_provider": "anthropic",
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 412,
            "output_tokens": 96,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    },
    usage_metadata={
        "input_tokens": 412,
        "output_tokens": 96,
        "total_tokens": 508,
        "input_token_details": {"cache_creation": 0, "cache_read": 0},
    },
)

_TOOL_MESSAGE = ToolMessage(
    content="Paris: sunny, 21C",
    tool_call_id="toolu_01A09q90qw90lq917835lq9",
    name="weather",
    artifact={"city": "Paris", "temp_c": 21, "conditions": ["sunny"]},
)

_UPDATE: Command[typing.Any] = Command(
    update={
        "messages": [
            ToolMessage(content="ok", tool_call_id="call_1", name="cmd")
        ],
        "extra_key": 123,
        "notes": {"a": [1, 2]},
    }
)


def _fixture(name: str) -> object:
    return json.loads((_FIXTURES / f"{name}.json").read_text())


class Out(pydantic.BaseModel):
    text: str


def _request(
    fmt: ResponseFormat[typing.Any] | None,
) -> ModelRequest[typing.Any]:
    return ModelRequest(
        model=ScriptedModel(script=[], counters=Counters()),
        messages=[],
        response_format=fmt,
    )


def test_model_fixture() -> None:
    fixture = _fixture("model_v1")
    request = _request(ToolStrategy(Out))
    response = ModelResponse(result=[_AI], structured_response=Out(text="hi"))

    replayed = step_output.replay_model(request, "model-0", fixture)
    assert replayed.result == [_AI]
    assert replayed.structured_response == Out(text="hi")
    assert step_output.record_model(request, response) == fixture


@pytest.mark.parametrize(
    ("name", "tool", "result"),
    [
        ("tool_message_v1", "weather", _TOOL_MESSAGE),
        ("tool_update_v1", "cmd", _UPDATE),
    ],
)
def test_tool_fixture(name: str, tool: str, result: object) -> None:
    fixture = _fixture(name)
    assert step_output.replay_tool("tool-0.0", fixture) == result
    assert step_output.record_tool(tool, result) == fixture


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"v": 2}, id="newer-version"),
        pytest.param({"extra": 1}, id="unknown-field"),
        pytest.param({"kind": "other"}, id="unknown-kind"),
    ],
)
def test_unreadable_replay_is_not_retried(change: dict[str, object]) -> None:
    fixture = _fixture("tool_message_v1")
    assert isinstance(fixture, dict)
    with pytest.raises(inngest.NonRetriableError, match="can't read"):
        step_output.replay_tool("tool-0.0", {**fixture, **change})


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(object(), id="object"),
        pytest.param(b"\xff", id="bytes"),
    ],
)
def test_unserializable_output_is_not_retried(artifact: object) -> None:
    message = ToolMessage(content="ok", tool_call_id="c", artifact=artifact)
    with pytest.raises(inngest.NonRetriableError, match="JSON"):
        step_output.record_tool("t", message)
    with pytest.raises(inngest.NonRetriableError, match="JSON"):
        step_output.record_model(
            _request(None),
            ModelResponse(result=[AIMessage(content="x", artifact=artifact)]),
        )


def test_non_json_values_change_type_on_replay() -> None:
    """A known limit: values that aren't JSON come back as JSON."""

    update: Command[typing.Any] = Command(update={"when": (1, 2)})
    data = step_output.record_tool("t", update)
    replayed = step_output.replay_tool("tool-0.0", data)
    assert isinstance(replayed, Command)
    assert typing.cast(dict[str, object], replayed.update) == {"when": [1, 2]}


# Structured output: every schema kind survives record and replay with its
# exact types, and anything that wouldn't is rejected when recorded.


class A(pydantic.BaseModel):
    text: str


class B(pydantic.BaseModel):
    text: str


class Aliased(pydantic.BaseModel):
    my_text: str = pydantic.Field(alias="myText")


class WithId(pydantic.BaseModel):
    text: str
    id: str = pydantic.Field(default_factory=lambda: uuid.uuid4().hex)


class Rich(pydantic.BaseModel):
    when: datetime.datetime
    uid: uuid.UUID
    amount: decimal.Decimal
    tags: set[str]
    pair: tuple[int, str]


@dataclasses.dataclass
class DC:
    text: str
    when: datetime.datetime


class TD(TypedDict):
    text: str
    when: datetime.datetime


class TDA(TypedDict):
    a: int


class TDB(TypedDict):
    b: int


class Color(enum.IntEnum):
    RED = 1


class Loose(pydantic.BaseModel):
    x: typing.Any


class Bang(pydantic.BaseModel):
    text: str

    @pydantic.field_validator("text")
    @classmethod
    def _bang(cls, v: str) -> str:
        return v + "!"


_WHEN = datetime.datetime(
    2026,
    11,
    4,
    12,
    34,
    56,
    123456,
    datetime.timezone(datetime.timedelta(hours=2)),
)
_TITLED = {
    "title": "JS",
    "type": "object",
    "properties": {"text": {"type": "string"}},
}
_UNTITLED = {"type": "object", "properties": {"text": {"type": "string"}}}


def _any(schema: object) -> typing.Any:
    """A union schema, which LangChain's annotations don't admit."""

    return schema


def _response(value: object, variant: str | None) -> ModelResponse[typing.Any]:
    """What the model node returns, with ToolStrategy's answer message."""

    result: list[typing.Any] = [AIMessage(content="")]
    if variant is not None:
        result.append(ToolMessage("ok", tool_call_id="c1", name=variant))
    return ModelResponse(result=result, structured_response=value)


def _round_trip(
    fmt: ResponseFormat[typing.Any], response: ModelResponse[typing.Any]
) -> tuple[dict[str, typing.Any], object]:
    request = _request(fmt)
    data = json.loads(json.dumps(step_output.record_model(request, response)))
    replayed = step_output.replay_model(request, "model-0", data)
    return data["structured"], replayed.structured_response


def _same(a: object, b: object) -> bool:
    return step_output._same(a, b)


@pytest.mark.parametrize(
    ("fmt", "value", "variant"),
    [
        pytest.param(ToolStrategy(A), A(text="hi"), "A", id="pydantic"),
        pytest.param(AutoStrategy(A), A(text="hi"), "A", id="bare"),
        pytest.param(ProviderStrategy(A), A(text="hi"), "A", id="provider"),
        pytest.param(ToolStrategy(A | B), B(text="hi"), "B", id="union"),
        pytest.param(
            AutoStrategy(_any(A | B)), B(text="hi"), "B", id="auto-union"
        ),
        pytest.param(
            ToolStrategy(_any(typing.Union[TDA, TDB])),  # noqa: UP007
            {"b": 1},
            "TDB",
            id="typeddict-union",
        ),
        pytest.param(
            ToolStrategy(Aliased), Aliased(myText="hi"), "Aliased", id="alias"
        ),
        pytest.param(
            ToolStrategy(WithId), WithId(text="hi"), "WithId", id="default"
        ),
        pytest.param(
            ToolStrategy(Rich),
            Rich(
                when=_WHEN,
                uid=uuid.UUID(int=7),
                amount=decimal.Decimal("1.10"),
                tags={"x", "y"},
                pair=(1, "a"),
            ),
            "Rich",
            id="rich",
        ),
        pytest.param(ToolStrategy(DC), DC("hi", _WHEN), "DC", id="dataclass"),
        pytest.param(
            ToolStrategy(TD),
            {"text": "hi", "when": _WHEN},
            "TD",
            id="typeddict",
        ),
        pytest.param(ToolStrategy(_TITLED), {"text": "hi"}, "JS", id="dict"),
        pytest.param(
            ToolStrategy(_UNTITLED), {"text": "hi"}, None, id="untitled-dict"
        ),
    ],
)
def test_structured_response_round_trip(
    fmt: ResponseFormat[typing.Any], value: object, variant: str | None
) -> None:
    stored, replayed = _round_trip(fmt, _response(value, variant))
    assert stored["variant"] == variant
    assert _same(replayed, value), (replayed, value)


def test_structured_response_is_stored_by_field_name() -> None:
    stored, _ = _round_trip(
        ToolStrategy(Aliased), _response(Aliased(myText="hi"), "Aliased")
    )
    assert stored["value"] == {"my_text": "hi"}


@pytest.mark.parametrize(
    ("fmt", "value", "match"),
    [
        pytest.param(
            ToolStrategy(Loose),
            Loose(x=Color.RED),
            "would replay as",
            id="intenum-in-any",
        ),
        pytest.param(
            ToolStrategy(Bang),
            Bang(text="hi"),
            "would replay as",
            id="validator",
        ),
        pytest.param(
            ToolStrategy(Loose), Loose(x=object()), "JSON", id="not-json"
        ),
    ],
)
def test_unfaithful_structured_response_is_rejected(
    fmt: ResponseFormat[typing.Any], value: pydantic.BaseModel, match: str
) -> None:
    with pytest.raises(inngest.NonRetriableError, match=match):
        step_output.record_model(
            _request(fmt), _response(value, type(value).__name__)
        )


def test_unknown_union_variant_is_rejected_when_recorded() -> None:
    with pytest.raises(inngest.NonRetriableError, match="can't tell"):
        step_output.record_model(
            _request(ToolStrategy(A | B)), _response(A(text="hi"), None)
        )


@pytest.mark.parametrize(
    ("replay_fmt", "change", "match"),
    [
        pytest.param(ToolStrategy(A), {}, "no longer has", id="variant-gone"),
        pytest.param(
            ToolStrategy(A | B),
            {"value": {"text": 5}},
            "no longer accepts",
            id="bad-value",
        ),
        pytest.param(
            ToolStrategy(_UNTITLED), {}, "no longer has", id="now-a-dict"
        ),
    ],
)
def test_unreadable_structured_response_is_not_retried(
    replay_fmt: ResponseFormat[typing.Any],
    change: dict[str, object],
    match: str,
) -> None:
    data = step_output.record_model(
        _request(ToolStrategy(A | B)), _response(B(text="hi"), "B")
    )
    structured = data["structured"]
    assert isinstance(structured, dict)
    data["structured"] = {**structured, **change}
    with pytest.raises(inngest.NonRetriableError, match=match):
        step_output.replay_model(_request(replay_fmt), "model-0", data)


@pytest.mark.parametrize("is_sync", [False, True], ids=["async", "sync"])
@pytest.mark.parametrize(
    ("fmt", "script", "expected"),
    [
        pytest.param(
            ToolStrategy(A | B),
            [tool_turn(call("B", "c1", text="hi"))],
            B(text="hi"),
            id="tool-union",
        ),
        pytest.param(
            ProviderStrategy(Aliased),
            [AIMessage(content='{"myText": "hi"}')],
            Aliased(myText="hi"),
            id="provider-alias",
        ),
    ],
)
def test_structured_response_through_the_agent(
    is_sync: bool,
    fmt: ResponseFormat[typing.Any],
    script: list[AIMessage | Exception],
    expected: object,
) -> None:
    c, run = Counters(), FakeRun()
    res, exc, _ = drive(run, is_sync, script, list, c, response_format=fmt)
    assert exc is None and res is not None
    assert _same(res["structured_response"], expected)
    assert c.model == 1
