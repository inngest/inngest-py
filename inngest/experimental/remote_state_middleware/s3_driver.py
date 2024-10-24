import json
import secrets
import string
import typing

import boto3
import pydantic

import inngest

from .middleware import StateDriver


class _StatePlaceholder(pydantic.BaseModel):
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

    def __init__(  # noqa: D107
        self,
        *,
        bucket: str,
        endpoint_url: typing.Optional[str] = None,
        region_name: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
        )

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

            step.data = json.loads(
                self._client.get_object(
                    Bucket=placeholder.bucket,
                    Key=placeholder.key,
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
        """

        key = f"inngest/remote_state/{run_id}/{self._create_key()}"
        self._client.create_bucket(Bucket=self._bucket)
        self._client.put_object(
            Body=json.dumps(value),
            Bucket=self._bucket,
            Key=key,
        )

        placeholder: dict[str, object] = {
            self._marker: True,
            self._strategy_marker: self._strategy_identifier,
            **_StatePlaceholder(bucket=self._bucket, key=key).model_dump(),
        }

        return placeholder
