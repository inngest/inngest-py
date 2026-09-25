"""
Session metadata lifecycle at the SDK boundary.

The server resolves incoming metadata into ``meta.sessions`` before invoking
the SDK. We intersect those resolved sessions across triggering events to
initialize ``ctx.sessions``. Outgoing sends copy the current context sessions
into ``meta.propagated_sessions`` and retain explicit ``meta.sessions`` overrides.
The server applies those overrides; this module does not merge the two outgoing
layers. A tombstone (``None``) explicitly removes an inherited session, or all
inherited sessions when used for the whole ``sessions`` field.
"""

from __future__ import annotations

import math
import typing

import jcs
import typing_extensions

from inngest._internal import run_context

if typing.TYPE_CHECKING:
    from inngest._internal import server_lib


class EventMeta(typing_extensions.TypedDict, total=False):
    """Session overrides and the SDK's inherited session layer."""

    sessions: dict[str, str | int | float | None] | None
    propagated_sessions: dict[str, str | int | float]


@typing.overload
def normalize_sessions(
    value: object, *, allow_tombstones: typing.Literal[True]
) -> dict[str, str | None]: ...


@typing.overload
def normalize_sessions(
    value: object, *, allow_tombstones: typing.Literal[False]
) -> dict[str, str]: ...


def normalize_sessions(
    value: object, *, allow_tombstones: bool
) -> dict[str, str] | dict[str, str | None]:
    """Validate a session map; only explicit overrides may contain tombstones."""
    if not isinstance(value, dict):
        raise ValueError("Event sessions must be an object")
    result: dict[str, str | None] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Event session keys must be non-empty strings")
        if item is None and allow_tombstones:
            result[key] = None
            continue
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            raise ValueError(
                "Event session IDs must be strings or finite numbers"
            )
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Event session IDs must be finite")
        if isinstance(item, str):
            normalized = item
        else:
            # JCS uses ECMAScript number formatting, including exponent cutoffs
            # and negative zero. This SDK already uses it for canonical JSON.
            try:
                encoded = jcs.canonicalize(item)
            except (OverflowError, ValueError) as err:
                raise ValueError("Event session IDs must be finite") from err
            if not isinstance(encoded, bytes):
                raise ValueError("Could not normalize numeric session ID")
            normalized = encoded.decode("utf-8")
        if not normalized:
            raise ValueError("Event session IDs cannot be empty")
        result[key] = normalized
    return result


def normalize_meta(value: object) -> EventMeta | None:
    """Normalize wire metadata without converting absent fields to null."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Event meta must be an object")
    out: EventMeta = {}
    # Absent means inherit; null clears all; an empty map adds no overrides.
    if "sessions" in value:
        if value["sessions"] is None:
            out["sessions"] = None
        else:
            overrides = normalize_sessions(
                value["sessions"], allow_tombstones=True
            )
            if overrides != {}:
                out["sessions"] = dict(overrides)
    # Null and empty propagation both mean there is no inherited layer.
    propagated = value.get("propagated_sessions")
    if propagated is not None:
        inherited = normalize_sessions(propagated, allow_tombstones=False)
        if inherited != {}:
            out["propagated_sessions"] = dict(inherited)
    return out or None


def get_shared_sessions(events: list[server_lib.Event]) -> dict[str, str]:
    """
    Intersect server-resolved ``meta.sessions``, capped at five sorted keys.

    Incoming ``propagated_sessions`` is not merged here: the server has already
    resolved it and any explicit overrides into ``sessions``.
    """
    shared: dict[str, str] | None = None
    for event in events:
        layer = (event.meta or {}).get("sessions") or {}
        own = {
            key: str(value) for key, value in layer.items() if value is not None
        }
        shared = (
            own
            if shared is None
            else {
                key: value
                for key, value in shared.items()
                if own.get(key) == value
            }
        )
    return dict(
        sorted(
            (shared or {}).items(), key=lambda item: item[0].encode("utf-8")
        )[:5]
    )


def stamp_meta(
    meta: EventMeta | None,
    *,
    inherited_sessions: dict[str, str] | None,
    preserve_existing_propagation: bool = False,
) -> EventMeta | None:
    """
    Copy explicit inputs into outgoing metadata without merging its layers.

    The client preserves propagation already stamped by a step, including any
    changes made by the step's send middleware before the client is called.
    """
    if inherited_sessions is None or (
        preserve_existing_propagation
        and meta is not None
        and "propagated_sessions" in meta
    ):
        return normalize_meta(meta)
    inherited = normalize_sessions(inherited_sessions, allow_tombstones=False)
    if inherited == {}:
        return normalize_meta(meta)
    return normalize_meta({**(meta or {}), "propagated_sessions": inherited})


def stamp_events(
    events: server_lib.Event | list[server_lib.Event],
    *,
    preserve_existing_propagation: bool = False,
) -> list[server_lib.Event]:
    """
    Snapshot the current ``ctx.sessions`` at send time into copied metadata.

    Steps stamp before send middleware runs. The client's second stamp must
    preserve that propagation, including middleware edits. Event payloads are
    shared rather than deep-copied.
    """
    inherited_sessions = run_context.get_sessions()
    return [
        event.model_copy(
            update={
                "meta": stamp_meta(
                    event.meta,
                    inherited_sessions=inherited_sessions,
                    preserve_existing_propagation=preserve_existing_propagation,
                )
            },
        )
        for event in (events if isinstance(events, list) else [events])
    ]
