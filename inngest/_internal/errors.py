from __future__ import annotations

from pydantic import ValidationError

from .const import ErrorCode


class InternalError(Exception):
    code: str
    status_code: int = 500

    def __init__(self, *, code: ErrorCode, message: str | None = None) -> None:
        super().__init__(message)
        self.code = code.value


class InvalidBaseURL(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_BASE_URL,
            message=message,
        )


class InvalidConfig(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_FUNCTION_CONFIG,
            message=message,
        )

    @classmethod
    def from_validation_error(
        cls,
        err: ValidationError,
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


class InvalidRequestSignature(InternalError):
    status_code: int = 401

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_REQUEST_SIGNATURE,
            message=message,
        )


class InvalidResponseShape(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_RESPONSE_SHAPE,
            message=message,
        )


class MissingEventKey(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_EVENT_KEY,
            message=message,
        )


class MissingFunction(InternalError):
    status_code: int = 400

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_FUNCTION,
            message=message,
        )


class MissingHeader(InternalError):
    status_code: int = 400

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingParam(InternalError):
    status_code: int = 400

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingSigningKey(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_SIGNING_KEY,
            message=message,
        )


class UnserializableOutput(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.UNSERIALIZABLE_OUTPUT,
            message=message,
        )


class ExternalError(Exception):
    pass


class NonRetriableError(ExternalError):
    """
    End users can raise this error to prevent retries.
    """
