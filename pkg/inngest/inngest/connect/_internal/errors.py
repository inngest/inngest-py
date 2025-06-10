class _NonRetryableError(Exception):
    pass


class _UnreachableError(Exception):
    """
    Should never be raised. If it is, it indicates a bug in the code.
    """

    pass
