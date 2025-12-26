import dataclasses
import json

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.usage import RequestUsage

import inngest


class Serializer(inngest.Serializer):
    def __init__(self) -> None:
        super().__init__()
        self._pydantic_serializer = inngest.PydanticSerializer()

    def serialize(self, obj: object, typ: object) -> object:
        if not dataclasses.is_dataclass(obj):
            return obj

        return json.loads(
            json.dumps(
                dataclasses.asdict(obj),  # type: ignore[arg-type]
                default=str,
            ),
        )

    def deserialize(self, obj: object, typ: object) -> object:
        if not isinstance(obj, dict):
            return obj

        parts: list[ToolCallPart | TextPart] = []
        for part in obj["parts"]:
            kind = part["part_kind"]
            del part["part_kind"]
            if kind == "tool-call":
                parts.append(ToolCallPart(**part))
            elif kind == "text":
                parts.append(TextPart(**part))
            else:
                raise ValueError(f"Unknown part kind: {part['part_kind']}")

        return ModelResponse(
            **{
                **obj,
                "parts": parts,
                "usage": RequestUsage(**obj["usage"]),
            }
        )
