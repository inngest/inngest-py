from __future__ import annotations

import http

import pydantic

from . import const


class InternalError(Exception):
    code: const.ErrorCode
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, *, code: const.ErrorCode, message: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class DevServerRegistrationNotAllowed(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.DISALLOWED_REGISTRATION_INITIATOR,
            message=message,
        )


class InvalidBaseURL(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_BASE_URL,
            message=message,
        )


class InvalidConfig(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_FUNCTION_CONFIG,
            message=message,
        )

    @classmethod
    def from_validation_error(
        cls,
        err: pydantic.ValidationError,
    ) -> InvalidConfig:
        """
        Extract info from Pydantic's ValidationError and return our internal
        InvalidFunctionConfig error.
        """
        default = cls(str(err))

        errors = err.errors()
        if len(errors) == 0:
            return default
        loc = errors[0].get("loc")
        if loc is None or len(loc) == 0:
            return default

        field = ""
        for part in loc:
            if isinstance(part, int):
                return default
            if len(field) > 0:
                field += "."
            field += part

        msg = errors[0].get("msg")
        if msg is None:
            return default

        return cls(f"{loc[0]}: {msg}")


class MismatchedSync(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISMATCHED_SYNC,
            message=message,
        )


class InvalidRequestSignature(InternalError):
    status_code: int = http.HTTPStatus.UNAUTHORIZED

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_REQUEST_SIGNATURE,
            message=message,
        )


class InvalidBody(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_BODY,
            message=message,
        )


class InvalidTransform(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_TRANSFORM,
            message=message,
        )


class MissingEventKey(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_EVENT_KEY,
            message=message,
        )


class MissingFunction(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_FUNCTION,
            message=message,
        )


class MissingHeader(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingParam(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingSigningKey(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_SIGNING_KEY,
            message=message,
        )


class RegistrationError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.REGISTRATION_ERROR,
            message=message,
        )


class UnknownError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.UNKNOWN,
            message=message,
        )


class UnserializableOutput(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.UNSERIALIZABLE_OUTPUT,
            message=message,
        )


class ExternalError(Exception):
    pass


class NonRetriableError(ExternalError):
    """End users can raise this error to prevent retries."""
