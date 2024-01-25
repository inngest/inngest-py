from __future__ import annotations

import http
import typing

import pydantic

from . import const, transforms


class Error(Exception):
    """
    Base error for all our custom errors
    """

    include_stack: bool = True
    is_retriable: bool = True

    @property
    def message(self) -> str:
        return str(self)

    @property
    def name(self) -> str:
        return type(self).__name__

    @property
    def stack(self) -> str | None:
        if self.include_stack is False:
            return None

        return transforms.get_traceback(self)


class InternalError(Error):
    """
    Base error for all errors that need an error code
    """

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


class UnexpectedStepError(InternalError):
    include_stack = False
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.UNEXPECTED_STEP,
            message=message,
        )


class UnserializableOutputError(InternalError):
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=const.ErrorCode.UNSERIALIZABLE_OUTPUT,
            message=message,
        )


class NonRetriableError(Error):
    """End users can raise this error to prevent retries."""

    is_retriable = False

    def __init__(
        self,
        message: str | None = None,
        cause: typing.Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause


class StepError(Error):
    """
    Wraps a userland error. This is necessary because the Executor sends
    memoized error data which can't be deserialized into the original error
    class.
    """

    # Not retriable since this error is thrown after exhausting retries
    is_retriable = False

    @property
    def message(self) -> str:
        """
        Returns the userland error message
        """

        return self._message

    @property
    def name(self) -> str:
        """
        Returns the userland error name
        """

        return self._name

    @property
    def stack(self) -> str | None:
        """
        Returns the userland error stack trace
        """

        return self._stack

    def __init__(
        self,
        message: str,
        name: str,
        stack: str | None,
    ) -> None:
        """
        Args:
        ----
            message: Userland error's message
            name: Userland error's name
            stack: Userland error's stack trace
        """

        super().__init__(message)
        self._message = message
        self._name = name
        self._stack = stack
