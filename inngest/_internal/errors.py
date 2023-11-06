from __future__ import annotations

import http

import pydantic

from . import const


class InternalError(Exception):
    code: const.ErrorCode
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(
        self, *, code: const.ErrorCode, message: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code


class DisallowedRegistrationError(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.DISALLOWED_REGISTRATION_INITIATOR,
            message=message,
        )


class InvalidBaseURLError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_BASE_URL,
            message=message,
        )


class InvalidConfigError(InternalError):
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
    ) -> InvalidConfigError:
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


class MismatchedSyncError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISMATCHED_SYNC,
            message=message,
        )


class InvalidRequestSignatureError(InternalError):
    status_code: int = http.HTTPStatus.UNAUTHORIZED

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_REQUEST_SIGNATURE,
            message=message,
        )


class InvalidBodyError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.INVALID_BODY,
            message=message,
        )


class MissingEventKeyError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_EVENT_KEY,
            message=message,
        )


class MissingFunctionError(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_FUNCTION,
            message=message,
        )


class MissingHeaderError(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingParamError(InternalError):
    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingSigningKeyError(InternalError):
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


class UnserializableOutputError(InternalError):
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
