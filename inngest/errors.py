from .const import ErrorCode


class InngestError(Exception):
    code: ErrorCode

    def __init__(self, *, code: ErrorCode, message: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class InvalidBaseURL(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_BASE_URL,
            message=message,
        )


class InvalidRequestSignature(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_REQUEST_SIGNATURE,
            message=message,
        )


class InvalidResponseShape(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_RESPONSE_SHAPE,
            message=message,
        )


class MissingEventKey(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_EVENT_KEY,
            message=message,
        )


class MissingFunction(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_FUNCTION,
            message=message,
        )


class MissingHeader(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingParam(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_HEADER,
            message=message,
        )


class MissingSigningKey(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.MISSING_SIGNING_KEY,
            message=message,
        )


class NonRetriableError(InngestError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.NON_RETRIABLE_ERROR,
            message=message,
        )
