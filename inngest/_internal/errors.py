from __future__ import annotations

import datetime
import typing

import pydantic

from inngest._internal import server_lib, transforms


class Error(Exception):
    """
    Base error for all our custom errors
    """

    code: server_lib.ErrorCode = server_lib.ErrorCode.UNKNOWN
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
    code = server_lib.ErrorCode.URL_INVALID


class FunctionConfigInvalidError(Error):
    code = server_lib.ErrorCode.FUNCTION_CONFIG_INVALID

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
    code = server_lib.ErrorCode.ASYNC_UNSUPPORTED


class SigVerificationFailedError(Error):
    code = server_lib.ErrorCode.SIG_VERIFICATION_FAILED


class BodyInvalidError(Error):
    code = server_lib.ErrorCode.BODY_INVALID


class EventKeyUnspecifiedError(Error):
    code = server_lib.ErrorCode.EVENT_KEY_UNSPECIFIED


class FunctionNotFoundError(Error):
    code = server_lib.ErrorCode.FUNCTION_NOT_FOUND


class HeaderMissingError(Error):
    code = server_lib.ErrorCode.HEADER_MISSING


class QueryParamMissingError(Error):
    code = server_lib.ErrorCode.QUERY_PARAM_MISSING


class SigningKeyMissingError(Error):
    code = server_lib.ErrorCode.SIGNING_KEY_UNSPECIFIED


class RegistrationFailedError(Error):
    code = server_lib.ErrorCode.REGISTRATION_FAILED


class UnknownError(Error):
    code = server_lib.ErrorCode.UNKNOWN


class StepUnexpectedError(Error):
    code = server_lib.ErrorCode.STEP_UNEXPECTED
    include_stack = False


class OutputUnserializableError(Error):
    code = server_lib.ErrorCode.OUTPUT_UNSERIALIZABLE


class NonRetriableError(Error):
    """End users can raise this error to prevent retries."""

    code = server_lib.ErrorCode.NON_RETRIABLE_ERROR
    is_retriable = False

    def __init__(
        self,
        message: typing.Optional[str] = None,
        quiet: bool = False,
    ) -> None:
        super().__init__(message)
        self.quiet = quiet


class RetryAfterError(Error):
    code = server_lib.ErrorCode.RETRY_AFTER_ERROR

    def __init__(
        self,
        message: typing.Optional[str],
        retry_after: typing.Union[int, datetime.timedelta, datetime.datetime],
        quiet: bool = False,
    ) -> None:
        """
        Raise this error to retry at a specific time.

        Args:
        ----
            message: Error message
            retry_after: Time to retry after in milliseconds, timedelta, or datetime
            quiet: Whether to supress logging
        """

        super().__init__(message)

        if isinstance(retry_after, int):
            retry_after = datetime.datetime.now() + datetime.timedelta(
                milliseconds=retry_after
            )
        elif isinstance(retry_after, datetime.timedelta):
            retry_after = datetime.datetime.now() + retry_after

        self.retry_after: datetime.datetime = retry_after
        self.quiet: bool = quiet


class SendEventsError(Error):
    code = server_lib.ErrorCode.SEND_EVENT_FAILED

    def __init__(self, message: str, ids: list[str]) -> None:
        """
        Args:
        ----
            message: Error message
            ids: List of event IDs that successfully sent
        """

        super().__init__(message)
        self.ids = ids


class StepError(Error):
    """
    Wraps a userland error. This is necessary because the Executor sends
    memoized error data which can't be deserialized into the original error
    class.
    """

    code = server_lib.ErrorCode.STEP_ERRORED

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


def is_retriable(err: Exception) -> bool:
    if isinstance(err, Error):
        return err.is_retriable
    return True


def is_quiet(err: Exception) -> bool:
    if isinstance(err, _Quietable):
        return err.quiet
    return False


@typing.runtime_checkable
class _Quietable(typing.Protocol):
    quiet: bool
