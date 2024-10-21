from __future__ import annotations

import http
import typing

from inngest._internal import net, server_lib, types

from .models import CommRequest, CommResponse

if typing.TYPE_CHECKING:
    from .handler import CommHandler


class _QueryParams(types.BaseModel):
    fn_id: typing.Optional[str]
    probe: typing.Optional[server_lib.Probe]
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

    probe: typing.Optional[server_lib.Probe] = None
    probe_str = normalized.get(server_lib.QueryParamKey.PROBE.value)
    if probe_str:
        try:
            probe = server_lib.Probe(probe_str)
        except ValueError:
            return Exception(f"unsupported probe: {probe_str}")

    step_id = normalized.get(server_lib.QueryParamKey.STEP_ID.value)
    if step_id == server_lib.UNSPECIFIED_STEP_ID:
        step_id = None

    return _QueryParams(
        fn_id=normalized.get(server_lib.QueryParamKey.FUNCTION_ID.value),
        probe=probe,
        step_id=step_id,
        sync_id=normalized.get(server_lib.QueryParamKey.SYNC_ID.value),
    )


_MethodHandler = typing.Callable[
    [typing.Any, CommRequest, types.MaybeError[typing.Optional[str]]],
    typing.Awaitable[typing.Union[CommResponse, Exception]],
]


def wrap_handler(
    require_signature: bool = True,
) -> typing.Callable[
    [_MethodHandler],
    typing.Callable[[typing.Any, CommRequest], typing.Awaitable[CommResponse]],
]:
    def decorator(
        method: _MethodHandler,
    ) -> typing.Callable[
        [typing.Any, CommRequest], typing.Awaitable[CommResponse]
    ]:
        """
        Perform request signature validation, error handling, header setting, and
        response signing.
        """

        async def wrapper(
            self: CommHandler,
            req: CommRequest,
        ) -> CommResponse:
            req.headers = net.normalize_headers(req.headers)

            request_signing_key = net.validate_request_sig(
                body=req.body,
                headers=req.headers,
                mode=self._client._mode,
                signing_key=self._signing_key,
                signing_key_fallback=self._signing_key_fallback,
            )
            if isinstance(request_signing_key, Exception) and require_signature:
                return CommResponse.from_error(
                    self._client.logger,
                    request_signing_key,
                    status=http.HTTPStatus.UNAUTHORIZED,
                )

            res = await method(
                self,
                req,
                request_signing_key,
            )
            if isinstance(res, Exception):
                res = CommResponse.from_error(self._client.logger, res)

            res.headers = {
                **res.headers,
                **net.create_headers(
                    env=self._client.env,
                    framework=self._framework,
                    server_kind=self._client._mode,
                ),
            }

            if isinstance(request_signing_key, str):
                err = res.sign(request_signing_key)
                if err is not None:
                    self._client.logger.error(err)

            return res

        return wrapper

    return decorator


_MethodHandlerSync = typing.Callable[
    [typing.Any, CommRequest, types.MaybeError[typing.Optional[str]]],
    typing.Union[CommResponse, Exception],
]


def wrap_handler_sync(
    require_signature: bool = True,
) -> typing.Callable[
    [_MethodHandlerSync],
    typing.Callable[[typing.Any, CommRequest], CommResponse],
]:
    def decorator(
        method: _MethodHandlerSync,
    ) -> typing.Callable[[typing.Any, CommRequest], CommResponse]:
        """
        Perform request signature validation, error handling, header setting, and
        response signing.
        """

        def wrapper(
            self: CommHandler,
            req: CommRequest,
        ) -> CommResponse:
            req.headers = net.normalize_headers(req.headers)

            request_signing_key = net.validate_request_sig(
                body=req.body,
                headers=req.headers,
                mode=self._client._mode,
                signing_key=self._signing_key,
                signing_key_fallback=self._signing_key_fallback,
            )
            if isinstance(request_signing_key, Exception) and require_signature:
                return CommResponse.from_error(
                    self._client.logger,
                    request_signing_key,
                    status=http.HTTPStatus.UNAUTHORIZED,
                )

            res = method(
                self,
                req,
                request_signing_key,
            )
            if isinstance(res, Exception):
                res = CommResponse.from_error(self._client.logger, res)

            res.headers = {
                **res.headers,
                **net.create_headers(
                    env=self._client.env,
                    framework=self._framework,
                    server_kind=self._client._mode,
                ),
            }

            if isinstance(request_signing_key, str):
                err = res.sign(request_signing_key)
                if err is not None:
                    self._client.logger.error(err)

            return res

        return wrapper

    return decorator
