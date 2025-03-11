import secrets
import string
import typing

import inngest
import pydantic

from ._internal import StateDriver


class _StatePlaceholder(pydantic.BaseModel):
    key: str


class InMemoryDriver(StateDriver):
    """
    In-memory driver for remote state middleware. This probably doesn't have any
    use besides being a reference.
    """

    # Marker to indicate that the data is stored remotely.
    _marker: typing.Final = "__REMOTE_STATE__"

    # Marker to indicate which strategy was used. This is useful for knowing
    # whether the official S3 driver was used.
    _strategy_marker: typing.Final = "__STRATEGY__"

    _strategy_identifier: typing.Final = "inngest/memory"

    def __init__(self) -> None:  # noqa: D107
        self._data: dict[str, object] = {}

    def _create_key(self) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(32))

    def load_steps(self, steps: inngest.StepMemos) -> None:
        """
        Hydrate steps with remote state if necessary.
        """

        for step in steps.values():
            if not isinstance(step.data, dict):
                continue
            if self._marker not in step.data:
                continue
            if self._strategy_marker not in step.data:
                continue
            if step.data[self._strategy_marker] != self._strategy_identifier:
                continue

            placeholder = _StatePlaceholder.model_validate(step.data)

            step.data = self._data[placeholder.key]

    def save_step(
        self,
        run_id: str,
        value: object,
    ) -> dict[str, object]:
        """
        Save a step's output to the remote store and return a placeholder.
        """

        key = self._create_key()
        self._data[key] = value

        placeholder: dict[str, object] = {
            self._marker: True,
            self._strategy_marker: self._strategy_identifier,
            **_StatePlaceholder(key=key).model_dump(),
        }

        return placeholder
