from .const import ErrorCode


class InternalError(Exception):
    code: ErrorCode
    status_code: int = 500

    def __init__(self, *, code: ErrorCode, message: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class InvalidBaseURL(InternalError):
    status_code: int = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_BASE_URL,
            message=message,
        )


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


class ExternalError(Exception):
    pass


class NonRetriableError(ExternalError):
    """
    End users can raise this error to prevent retries.
    """
