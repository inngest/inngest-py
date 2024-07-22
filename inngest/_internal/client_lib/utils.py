import typing

from inngest._internal import const, env_lib, net, server_lib, types


def get_api_origin(
    constructor_param: typing.Optional[str],
    mode: server_lib.ServerKind,
) -> types.MaybeError[str]:
    """
    Get the API origin, properly considering precedence.

    Args:
    ----
        constructor_param: Inngest client constructor's api_base_url param.
        mode: Server mode.
    """

    origin = (
        constructor_param
        or env_lib.get_url(const.EnvKey.API_BASE_URL, mode)
        or env_lib.get_url(const.EnvKey.BASE_URL, mode)
        or env_lib.get_url(const.EnvKey.DEV, mode)
    )
    if origin is None:
        if mode == server_lib.ServerKind.DEV_SERVER:
            origin = const.DEV_SERVER_ORIGIN
        else:
            origin = const.DEFAULT_API_ORIGIN
    return net.parse_url(origin, mode)


def get_event_api_origin(
    constructor_param: typing.Optional[str],
    mode: server_lib.ServerKind,
) -> types.MaybeError[str]:
    """
    Get the Event API origin, properly considering precedence.

    Args:
    ----
        constructor_param: Inngest client constructor's event_api_base_url param.
        mode: Server mode.
    """

    origin = (
        constructor_param
        or env_lib.get_url(const.EnvKey.EVENT_API_BASE_URL, mode)
        or env_lib.get_url(const.EnvKey.BASE_URL, mode)
        or env_lib.get_url(const.EnvKey.DEV, mode)
    )
    if origin is None:
        if mode == server_lib.ServerKind.DEV_SERVER:
            origin = const.DEV_SERVER_ORIGIN
        else:
            origin = const.DEFAULT_EVENT_API_ORIGIN
    return net.parse_url(origin, mode)
