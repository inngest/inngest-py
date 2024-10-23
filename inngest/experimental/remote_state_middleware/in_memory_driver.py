import secrets
import string
import typing

import pydantic

import inngest

from .middleware import StateDriver


class _StatePlaceholder(pydantic.BaseModel):
    __REMOTE_STATE__: typing.Literal[True] = True
    key: str


class InMemoryDriver(StateDriver):
    """
    In-memory driver for remote state middleware.
    """

    # Marker to indicate that the data is stored remotely.
    _marker: typing.Final = "__REMOTE_STATE__"

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

            try:
                placeholder = _StatePlaceholder.model_validate(step.data)
            except pydantic.ValidationError:
                continue

            step.data = self._data[placeholder.key]

    def save_step(
        self,
        value: object,
    ) -> dict[str, object]:
        """
        Save a step's output to the remote store and return a placeholder.
        """

        key = self._create_key()
        self._data[key] = value

        placeholder: dict[str, object] = {
            self._marker: True,
            **_StatePlaceholder(key=key).model_dump(),
        }

        return placeholder
