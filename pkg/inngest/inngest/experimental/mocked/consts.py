import enum


class Status(enum.Enum):
    """
    Function run status.
    """

    COMPLETED = "Completed"
    FAILED = "Failed"


Timeout = object()
