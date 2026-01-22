class NonRetryableError(Exception):
    """
    An error that should not be retried.

    Retry logic should check for this error type and stop immediately rather
    than continuing to retry.
    """

    pass


class UnreachableError(Exception):
    """
    Should never be raised. If it is, it indicates a bug in the code.

    This is used for cases that should be logically impossible, such as
    exhaustive pattern matching where all cases are handled.
    """

    pass
