"""Session overrides and the child sessions the real server should resolve."""

import dataclasses

import inngest


@dataclasses.dataclass
class Scenario:
    name: str
    meta: inngest.EventMeta | None
    expected: dict[str, str]


parent_sessions = {"conversation": "chat-1", "user": "alice"}
scenarios = [
    Scenario("inherit", None, parent_sessions),
    Scenario("empty metadata", {}, parent_sessions),
    Scenario("empty overrides", {"sessions": {}}, parent_sessions),
    Scenario("remove all", {"sessions": None}, {}),
    Scenario(
        "remove conversation",
        {"sessions": {"conversation": None}},
        {"user": "alice"},
    ),
    Scenario(
        "replace conversation",
        {"sessions": {"conversation": "chat-2"}},
        {"conversation": "chat-2", "user": "alice"},
    ),
]
