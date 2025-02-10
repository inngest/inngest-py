class UnstubbedStepError(Exception):
    """
    Raised when a must-stub step is not stubbed
    """

    def __init__(self, step_id: str) -> None:
        """
        Args:
        ----
            step_id: Unmocked step ID.
        """

        super().__init__(f"step {step_id} is not stubbed")
