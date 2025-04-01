from __future__ import annotations

import http
import typing

from inngest._internal import (
    errors,
    execution_lib,
    net,
    server_lib,
    transforms,
    types,
)


class CommRequest(types.BaseModel):
    body: bytes
    headers: typing.Union[dict[str, str], dict[str, str]]

    # Is this a Connect request? (As opposed to our HTTP execution model)
    is_connect: bool = False

    query_params: typing.Union[dict[str, str], dict[str, list[str]]]
    raw_request: object
    request_url: str
    serve_origin: typing.Optional[str]
    serve_path: typing.Optional[str]


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

    @property
    def no_retry(self) -> bool:
        value = self.headers.get(server_lib.HeaderKey.NO_RETRY.value)
        if value == "true":
            return True
        return False

    @property
    def request_version(self) -> typing.Optional[int]:
        value = self.headers.get(server_lib.HeaderKey.REQUEST_VERSION.value)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def retry_after(self) -> typing.Optional[str]:
        return self.headers.get(server_lib.HeaderKey.RETRY_AFTER.value)

    @property
    def sdk_version(self) -> typing.Optional[str]:
        return self.headers.get(server_lib.HeaderKey.SDK.value)

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
                headers[server_lib.HeaderKey.RETRY_AFTER.value] = (
                    transforms.to_iso_utc(call_res.error.retry_after)
                )

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
            headers={
                server_lib.HeaderKey.CONTENT_TYPE.value: "application/json",
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

    def body_bytes(self) -> types.MaybeError[bytes]:
        dumped = transforms.dump_json(self.body)
        if isinstance(dumped, Exception):
            return dumped
        return dumped.encode("utf-8")

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
        body_bytes = self.body_bytes()
        if isinstance(body_bytes, Exception):
            return body_bytes

        sig = net.sign_response(body_bytes, signing_key)
        if isinstance(sig, Exception):
            return sig

        self.headers = {
            **self.headers,
            server_lib.HeaderKey.SIGNATURE.value: sig,
        }

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
