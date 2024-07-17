from __future__ import annotations

import http
import typing

from inngest._internal import (
    const,
    errors,
    execution_lib,
    net,
    server_lib,
    transforms,
    types,
)


class CommResponse:
    def __init__(
        self,
        *,
        body: object = None,
        headers: typing.Optional[dict[str, str]] = None,
        status_code: int = http.HTTPStatus.OK.value,
    ) -> None:
        self.headers = headers or {}
        self.body = body
        self.status_code = status_code

    @classmethod
    def from_call_result(
        cls,
        logger: types.Logger,
        call_res: execution_lib.CallResult,
        env: typing.Optional[str],
        framework: server_lib.Framework,
        server_kind: typing.Optional[server_lib.ServerKind],
    ) -> CommResponse:
        headers = {
            server_lib.HeaderKey.SERVER_TIMING.value: "handler",
            **net.create_headers(
                env=env,
                framework=framework,
                server_kind=server_kind,
            ),
        }

        if call_res.multi:
            multi_body: list[object] = []
            for item in call_res.multi:
                d = _prep_call_result(item)
                if isinstance(d, Exception):
                    return cls.from_error(logger, d)
                multi_body.append(d)

                if item.error is not None:
                    if errors.is_retriable(item.error) is False:
                        headers[server_lib.HeaderKey.NO_RETRY.value] = "true"

            return cls(
                body=multi_body,
                headers=headers,
                status_code=http.HTTPStatus.PARTIAL_CONTENT.value,
            )

        body = _prep_call_result(call_res)
        status_code = http.HTTPStatus.OK.value
        if isinstance(body, Exception):
            return cls.from_error(logger, body)

        if call_res.error is not None:
            status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR.value
            if errors.is_retriable(call_res.error) is False:
                headers[server_lib.HeaderKey.NO_RETRY.value] = "true"

            if isinstance(call_res.error, errors.RetryAfterError):
                headers[
                    server_lib.HeaderKey.RETRY_AFTER.value
                ] = transforms.to_iso_utc(call_res.error.retry_after)

        return cls(
            body=body,
            headers=headers,
            status_code=status_code,
        )

    @classmethod
    def from_error(
        cls,
        logger: types.Logger,
        err: Exception,
        status: http.HTTPStatus = http.HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> CommResponse:
        code: typing.Optional[str] = None
        if isinstance(err, errors.Error):
            code = err.code.value
        else:
            code = server_lib.ErrorCode.UNKNOWN.value

        if errors.is_quiet(err) is False:
            logger.error(f"{code}: {err!s}")

        return cls(
            body={
                "code": code,
                "message": str(err),
                "name": type(err).__name__,
            },
            status_code=status.value,
        )

    @classmethod
    def from_error_code(
        cls,
        code: server_lib.ErrorCode,
        message: str,
        status: http.HTTPStatus = http.HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> CommResponse:
        return cls(
            body={
                "code": code.value,
                "message": message,
            },
            status_code=status.value,
        )

    def prep_call_result(
        self,
        call_res: execution_lib.CallResult,
    ) -> types.MaybeError[object]:
        """
        Convert a CallResult to the shape the Inngest Server expects. For step-level
        results this is a dict and for function-level results this is the output or
        error.
        """

        if call_res.step is not None:
            d = call_res.step.to_dict()
            if isinstance(d, Exception):
                # Unreachable
                return d
        else:
            d = {}

        if call_res.error is not None:
            e = ErrorData.from_error(call_res.error).to_dict()
            if isinstance(e, Exception):
                return e
            d["error"] = e

        if call_res.output is not types.empty_sentinel:
            err = transforms.dump_json(call_res.output)
            if isinstance(err, Exception):
                msg = "returned unserializable data"
                if call_res.step is not None:
                    msg = f'"{call_res.step.display_name}" {msg}'

                return errors.OutputUnserializableError(msg)

            d["data"] = call_res.output

        is_function_level = call_res.step is None
        if is_function_level:
            # Don't nest function-level results
            return d.get("error") or d.get("data")

        return d

    def sign(self, signing_key: str) -> types.MaybeError[None]:
        byt: bytes
        if isinstance(self.body, bytes):
            byt = self.body
        else:
            dumped = transforms.dump_json(self.body)
            if isinstance(dumped, Exception):
                return dumped

            byt = dumped.encode("utf-8")

        self.headers[server_lib.HeaderKey.SIGNATURE.value] = net.sign(
            byt,
            signing_key,
        )

        return None


def _prep_call_result(
    call_res: execution_lib.CallResult,
) -> types.MaybeError[object]:
    """
    Convert a CallResult to the shape the Inngest Server expects. For step-level
    results this is a dict and for function-level results this is the output or
    error.
    """

    if call_res.step is not None:
        d = call_res.step.to_dict()
        if isinstance(d, Exception):
            # Unreachable
            return d
    else:
        d = {}

    if call_res.error is not None:
        e = ErrorData.from_error(call_res.error).to_dict()
        if isinstance(e, Exception):
            return e
        d["error"] = e

    if call_res.output is not types.empty_sentinel:
        err = transforms.dump_json(call_res.output)
        if isinstance(err, Exception):
            msg = "returned unserializable data"
            if call_res.step is not None:
                msg = f'"{call_res.step.display_name}" {msg}'

            return errors.OutputUnserializableError(msg)

        d["data"] = call_res.output

    is_function_level = call_res.step is None
    if is_function_level:
        # Don't nest function-level results
        return d.get("error") or d.get("data")

    return d


class ErrorData(types.BaseModel):
    code: server_lib.ErrorCode
    message: str
    name: str
    stack: typing.Optional[str]

    @classmethod
    def from_error(cls, err: Exception) -> ErrorData:
        if isinstance(err, errors.Error):
            code = err.code
            message = err.message
            name = err.name
            stack = err.stack
        else:
            code = server_lib.ErrorCode.UNKNOWN
            message = str(err)
            name = type(err).__name__
            stack = transforms.get_traceback(err)

        return cls(
            code=code,
            message=message,
            name=name,
            stack=stack,
        )


class UnauthenticatedInspection(types.BaseModel):
    schema_version: str = "2024-07-19"

    authentication_succeeded: typing.Optional[bool]
    function_count: int
    has_event_key: bool
    has_signing_key: bool
    has_signing_key_fallback: bool
    mode: server_lib.ServerKind


class AuthenticatedInspection(UnauthenticatedInspection):
    api_origin: str
    app_id: str
    authentication_succeeded: bool = True
    env: typing.Optional[str]
    event_api_origin: str
    event_key_hash: typing.Optional[str]
    framework: str
    sdk_language: str = const.LANGUAGE
    sdk_version: str = const.VERSION
    serve_origin: typing.Optional[str]
    serve_path: typing.Optional[str]
    signing_key_fallback_hash: typing.Optional[str]
    signing_key_hash: typing.Optional[str]
    supports_in_band_sync: bool = True
