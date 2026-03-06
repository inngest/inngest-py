from __future__ import annotations

import typing

from google.protobuf import message as pb_message

from inngest._internal import types

_T = typing.TypeVar("_T", bound=pb_message.Message)


def safe_parse(pb_class: type[_T], data: bytes) -> types.MaybeError[_T]:
    """
    Parse a protobuf message, returning an Exception on failure.
    """

    try:
        msg = pb_class()
        msg.ParseFromString(data)
        return msg
    except Exception as e:
        return e
