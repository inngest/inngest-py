import pydantic
import pytest

from . import event_lib


def test_data_missing() -> None:
    event_lib.Event(name="foo")


def test_data_list() -> None:
    with pytest.raises(pydantic.ValidationError):
        event_lib.Event(
            data=[1, 2, 3],  # type: ignore[arg-type]
            name="foo",
        )


def test_data_nested() -> None:
    event_lib.Event(
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
        event_lib.Event(
            data={
                "foo": object(),  # type: ignore[dict-item]
            },
            name="foo",
        )
