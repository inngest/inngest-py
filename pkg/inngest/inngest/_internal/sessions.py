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


def normalize_sessions(
    value: object, *, manual: bool
) -> dict[str, str | None] | None:
    """Validate IDs and preserve manual tombstones."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Event sessions must be an object")
    result: dict[str, str | None] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Event session keys must be non-empty strings")
        if item is None and manual:
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
    if "sessions" in value:
        manual = normalize_sessions(value["sessions"], manual=True)
        if manual or manual is None:
            out["sessions"] = (
                {key: item for key, item in manual.items()}
                if manual is not None
                else None
            )
    propagated = normalize_sessions(
        value.get("propagated_sessions"), manual=False
    )
    if propagated:
        out["propagated_sessions"] = {
            key: item for key, item in propagated.items() if item is not None
        }
    return out or None


def reduce_sessions(events: list[server_lib.Event]) -> dict[str, str]:
    """Intersect effective event sessions, deterministically capped at five."""
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
    meta: EventMeta | None, *, only_if_absent: bool = False
) -> EventMeta | None:
    """Copy the current sessions into an outgoing event's inherited layer."""
    run = run_context.current_run.get()
    if run is None or (
        only_if_absent and meta is not None and "propagated_sessions" in meta
    ):
        return normalize_meta(meta)
    inherited = normalize_sessions(run.ctx.sessions, manual=False)
    if not inherited:
        return normalize_meta(meta)
    return normalize_meta({**(meta or {}), "propagated_sessions": inherited})


def stamp_events(
    events: server_lib.Event | list[server_lib.Event],
    *,
    only_if_absent: bool = False,
) -> list[server_lib.Event]:
    """Copy events and session metadata without deep-copying user payloads."""
    return [
        event.model_copy(
            update={
                "meta": stamp_meta(event.meta, only_if_absent=only_if_absent)
            },
        )
        for event in (events if isinstance(events, list) else [events])
    ]
