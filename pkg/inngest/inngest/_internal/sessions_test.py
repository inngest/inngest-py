from __future__ import annotations

import json

import pydantic
import pytest

import inngest
from inngest._internal import sessions


def test_shared_sessions_ignore_unexpected_residual_propagation() -> None:
    """
    Defensive case: the server normally clears propagated_sessions when it
    resolves incoming metadata. If residual propagation reaches the SDK anyway,
    use only the resolved layer rather than restoring removed or replaced IDs.
    """
    event = inngest.Event(
        name="start",
        meta={
            "sessions": {"conversation": "resolved"},
            "propagated_sessions": {"conversation": "old", "removed": "old"},
        },
    )
    assert sessions.get_shared_sessions([event]) == {"conversation": "resolved"}


def test_shared_sessions_defensively_cap_oversized_input() -> None:
    """
    Defensive case: the server normally enforces five sessions per event, so a
    valid batch cannot exceed that limit. For oversized input, keep a stable
    five using UTF-8 key ordering, regardless of dictionary insertion order.
    This tests deterministic selection, not durable replay.
    """
    names = ["\U00010000", "\ue000", "a", "b", "c", "d"]
    expected = {key: "value" for key in ["a", "b", "c", "d", "\ue000"]}
    for order in [names, list(reversed(names))]:
        event = inngest.Event(
            name="start", meta={"sessions": {key: "value" for key in order}}
        )
        assert sessions.get_shared_sessions([event]) == expected, order


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


def test_session_group_names_cannot_be_empty() -> None:
    """
    Require a name for the grouping dimension, such as conversation or user.
    """

    with pytest.raises(
        pydantic.ValidationError, match="session keys must be non-empty strings"
    ):
        inngest.Event(name="e", meta={"sessions": {"": "chat-1"}})


def test_malformed_session_map_is_not_treated_as_no_overrides() -> None:
    """
    An empty list is a configuration error, not an empty override map. Silently
    dropping it during normalization would hide the mistake and allow
    inheritance.
    """

    with pytest.raises(
        pydantic.ValidationError, match="Event sessions must be an object"
    ):
        inngest.Event.model_validate({"name": "e", "meta": {"sessions": []}})


def test_propagated_session_ids_cannot_be_null() -> None:
    """
    Non-null inherited IDs are a protocol invariant: the backend should never
    send a null ID inside propagated_sessions. Reject such input rather than
    interpreting it as a removal instruction. Removing a specific session is
    valid in the explicit override layer: meta.sessions={"conversation": None}.
    """

    with pytest.raises(
        pydantic.ValidationError,
        match="session IDs must be strings or finite numbers",
    ):
        inngest.Event.model_validate(
            {
                "name": "e",
                "meta": {"propagated_sessions": {"conversation": None}},
            }
        )


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
