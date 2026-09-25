from __future__ import annotations

import json

import pydantic
import pytest

import inngest


def test_invalid_session_ids_are_not_coerced_into_grouping_keys() -> None:
    """
    Invalid IDs should fail where the developer builds the event, rather than
    silently grouping runs under a coerced value or failing later at ingestion.
    In particular, Python treats booleans as integers, but True must not become
    the numeric session ID "1". Non-finite numbers cannot be valid JSON numbers.
    """

    # Untrusted input intentionally has a broader type than EventMeta.
    cases: list[tuple[str, object, str]] = [
        ("boolean ID", True, "session IDs must be strings or finite numbers"),
        ("empty ID", "", "session IDs cannot be empty"),
        ("infinite ID", float("inf"), "session IDs must be finite"),
        ("NaN ID", float("nan"), "session IDs must be finite"),
    ]
    for name, value, expected_error in cases:
        with pytest.raises(pydantic.ValidationError) as raised:
            inngest.Event.model_validate(
                {"name": "e", "meta": {"sessions": {"conversation": value}}}
            )
        errors = raised.value.errors()
        assert len(errors) == 1, name
        assert errors[0]["loc"] == ("meta",), name
        assert expected_error in errors[0]["msg"], name


def test_numeric_session_ids_become_strings() -> None:
    """
    Accept numeric session IDs and normalizes them to strings before sending
    events. Equivalent IDs such as 1.0 and "1" should group runs together. This
    matches the TypeScript SDK's behavior.
    """

    cases: list[tuple[str, float, str]] = [
        ("integer-valued float", 1.0, "1"),
        ("negative zero", -0.0, "0"),
        ("large exponent", 1e21, "1e+21"),
        ("small exponent", 1e-7, "1e-7"),
        ("decimal cutoff", 1e-6, "0.000001"),
    ]
    for name, value, expected in cases:
        event = inngest.Event(name="e", meta={"sessions": {"id": value}})
        serialized = json.loads(event.model_dump_json())
        assert serialized["meta"]["sessions"]["id"] == expected, name
