import typing

from inngest._internal import server_lib, types


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

    step_id = normalized.get(server_lib.QueryParamKey.STEP_ID.value)
    if step_id == server_lib.UNSPECIFIED_STEP_ID:
        step_id = None

    return _QueryParams(
        fn_id=normalized.get(server_lib.QueryParamKey.FUNCTION_ID.value),
        step_id=step_id,
        sync_id=normalized.get(server_lib.QueryParamKey.SYNC_ID.value),
    )
