import pydantic
import pytest

from .event import Event


def test_data_missing() -> None:
    Event(name="foo")


def test_data_list() -> None:
    with pytest.raises(pydantic.ValidationError):
        Event(
            data=[1, 2, 3],  # type: ignore[arg-type]
            name="foo",
        )


def test_data_nested() -> None:
    Event(
        data={
            "foo": {
                "bar": {
                    "baz": 1,
                },
            },
        },
        name="foo",
    )


def test_data_invalid() -> None:
    with pytest.raises(pydantic.ValidationError):
        Event(
            data={
                "foo": object(),  # type: ignore[dict-item]
            },
            name="foo",
        )
