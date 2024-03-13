from __future__ import annotations

import typing

import pydantic

from . import const, transforms


class Error(Exception):
    """
    Base error for all our custom errors
    """

    code: const.ErrorCode
    include_stack: bool = True
    is_retriable: bool = True

    @property
    def message(self) -> str:
        return str(self)

    @property
    def name(self) -> str:
        return type(self).__name__

    @property
    def stack(self) -> typing.Optional[str]:
        if self.include_stack is False:
            return None

        return transforms.get_traceback(self)


class URLInvalidError(Error):
    code = const.ErrorCode.URL_INVALID


class FunctionConfigInvalidError(Error):
    code = const.ErrorCode.FUNCTION_CONFIG_INVALID

    @classmethod
    def from_validation_error(
        cls,
        err: pydantic.ValidationError,
    ) -> FunctionConfigInvalidError:
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


class AsyncUnsupportedError(Error):
    code = const.ErrorCode.ASYNC_UNSUPPORTED


class SigVerificationFailedError(Error):
    code = const.ErrorCode.SIG_VERIFICATION_FAILED


class BodyInvalidError(Error):
    code = const.ErrorCode.BODY_INVALID


class EventKeyUnspecifiedError(Error):
    code = const.ErrorCode.EVENT_KEY_UNSPECIFIED


class FunctionNotFoundError(Error):
    code = const.ErrorCode.FUNCTION_NOT_FOUND


class HeaderMissingError(Error):
    code = const.ErrorCode.HEADER_MISSING


class QueryParamMissingError(Error):
    code = const.ErrorCode.QUERY_PARAM_MISSING


class SigningKeyMissingError(Error):
    code = const.ErrorCode.SIGNING_KEY_UNSPECIFIED


class RegistrationFailedError(Error):
    code = const.ErrorCode.REGISTRATION_FAILED


class UnknownError(Error):
    code = const.ErrorCode.UNKNOWN


class StepUnexpectedError(Error):
    code = const.ErrorCode.STEP_UNEXPECTED
    include_stack = False


class OutputUnserializableError(Error):
    code = const.ErrorCode.OUTPUT_UNSERIALIZABLE


class NonRetriableError(Error):
    """End users can raise this error to prevent retries."""

    code = const.ErrorCode.NON_RETRIABLE_ERROR
    is_retriable = False

    def __init__(
        self,
        message: typing.Optional[str] = None,
        cause: typing.Optional[typing.Mapping[str, object]] = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause


class StepError(Error):
    """
    Wraps a userland error. This is necessary because the Executor sends
    memoized error data which can't be deserialized into the original error
    class.
    """

    code = const.ErrorCode.STEP_ERRORED

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
    def stack(self) -> typing.Optional[str]:
        """
        Returns the userland error stack trace
        """

        return self._stack

    def __init__(
        self,
        message: str,
        name: str,
        stack: typing.Optional[str],
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
