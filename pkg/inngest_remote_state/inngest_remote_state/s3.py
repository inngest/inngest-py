from __future__ import annotations

import json
import secrets
import string
import typing

import inngest
import pydantic
import typing_extensions

from ._internal import StateDriver

if typing.TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class _StateSurrogate(pydantic.BaseModel):
    """
    Replaces step output sent back to Inngest. Its data is sufficient to
    retrieve the actual state.
    """

    bucket: str
    key: str


class S3Driver(StateDriver):
    """
    S3 driver for remote state middleware.
    """

    # Marker to indicate that the data is stored remotely.
    _marker: typing.Final = "__REMOTE_STATE__"

    # Marker to indicate which strategy was used. This is useful for knowing
    # whether the official S3 driver was used.
    _strategy_marker: typing.Final = "__STRATEGY__"

    _strategy_identifier: typing.Final = "inngest/s3"

    def __init__(
        self,
        *,
        bucket: str,
        client: S3Client,
    ) -> None:
        """
        Args:
        ----
            bucket: Bucket name to store remote state.
            client: Boto3 S3 client.
        """

        self._bucket = bucket
        self._client = client

    def _create_key(self) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(32))

    def _is_remote(
        self, data: object
    ) -> typing_extensions.TypeGuard[dict[str, object]]:
        return (
            isinstance(data, dict)
            and self._marker in data
            and self._strategy_marker in data
            and data[self._strategy_marker] == self._strategy_identifier
        )

    def load_steps(self, steps: inngest.StepMemos) -> None:
        """
        Hydrate steps with remote state if necessary.

        Args:
        ----
            steps: Steps that may need hydration.
        """

        for step in steps.values():
            if not self._is_remote(step.data):
                continue

            surrogate = _StateSurrogate.model_validate(step.data)

            step.data = json.loads(
                self._client.get_object(
                    Bucket=surrogate.bucket,
                    Key=surrogate.key,
                )["Body"]
                .read()
                .decode()
            )

    def save_step(
        self,
        run_id: str,
        value: object,
    ) -> dict[str, object]:
        """
        Save a step's output to the remote store and return a placeholder.

        Args:
        ----
            run_id: Run ID.
            value: Step output.
        """

        key = f"inngest/remote_state/{run_id}/{self._create_key()}"
        self._client.put_object(
            Body=json.dumps(value),
            Bucket=self._bucket,
            Key=key,
        )

        surrogate = {
            self._marker: True,
            self._strategy_marker: self._strategy_identifier,
            **_StateSurrogate(bucket=self._bucket, key=key).model_dump(),
        }

        return surrogate
