from __future__ import annotations

import typing

from inngest._internal import types

from .consts import UNSPECIFIED_STEP_ID, QueryParamKey


class _QueryParams(types.BaseModel):
    fn_id: typing.Optional[str]
    step_id: typing.Optional[str]
    sync_id: typing.Optional[str]


def parse_query_params(
    query_params: typing.Union[dict[str, str], dict[str, list[str]]],
) -> typing.Union[_QueryParams, Exception]:
    normalized: dict[str, str] = {}
    for k, v in query_params.items():
        if isinstance(v, list):
            normalized[k] = v[0]
        else:
            normalized[k] = v

    step_id = normalized.get(QueryParamKey.STEP_ID.value)
    if step_id == UNSPECIFIED_STEP_ID:
        step_id = None

    return _QueryParams(
        fn_id=normalized.get(QueryParamKey.FUNCTION_ID.value),
        step_id=step_id,
        sync_id=normalized.get(QueryParamKey.SYNC_ID.value),
    )
