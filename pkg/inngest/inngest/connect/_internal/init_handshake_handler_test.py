import itertools
import json
import logging
import os
import subprocess
import sys
import textwrap

import pytest

import inngest
from inngest._internal import comm_lib, server_lib

from . import connect_pb2
from .init_handshake_handler import _create_sync_message
from .models import AppConfig


def _configs(
    ids: tuple[str, ...],
    *,
    app_id: str = "test",
    event: str = "demo/event",
    on_failure: bool = False,
) -> list[server_lib.FunctionConfig]:
    client = inngest.Inngest(
        app_id=app_id,
        is_production=False,
        logger=logging.getLogger("test"),
    )

    async def handler(ctx: inngest.Context) -> None:
        pass

    functions = [
        client.create_function(
            fn_id=fn_id,
            trigger=inngest.TriggerEvent(event=event),
            on_failure=handler if on_failure else None,
        )(handler)
        for fn_id in ids
    ]
    configs = comm_lib.get_function_configs(
        "wss://connect", {fn.id: fn for fn in functions}
    )
    assert not isinstance(configs, Exception)
    return configs


def _sync(apps: dict[str, AppConfig]) -> connect_pb2.WorkerConnectRequestData:
    message = _create_sync_message(
        app_configs=apps,
        auth_data=connect_pb2.AuthData(),
        connection_id="test",
        env=None,
        instance_id="test",
        max_worker_concurrency=None,
    )
    assert not isinstance(message, Exception)
    return connect_pb2.WorkerConnectRequestData.FromString(message.payload)


def test_function_order_does_not_change_sync_payload() -> None:
    payloads = set()
    for ids in itertools.permutations(("zebra", "alpha", "alpha-0")):
        configs = _configs(ids, on_failure=True)
        original = list(configs)
        payload = _sync({"test": AppConfig(configs, "same-code")})
        payloads.add(payload.apps[0].functions)
        assert configs == original
        assert all(a is b for a, b in zip(configs, original))

    assert len(payloads) == 1
    assert [fn["id"] for fn in json.loads(payloads.pop())] == [
        "test-alpha",
        "test-alpha-0",
        "test-alpha-0-failure",
        "test-alpha-failure",
        "test-zebra",
        "test-zebra-failure",
    ]


def test_apps_and_real_config_changes_remain_distinct() -> None:
    payload = _sync(
        {
            "first": AppConfig(
                _configs(("zebra", "alpha"), app_id="first"), "v1"
            ),
            "second": AppConfig(
                _configs(("zebra", "alpha"), app_id="second"), "v2"
            ),
        }
    )
    assert [app.app_name for app in payload.apps] == ["first", "second"]
    assert [app.app_version for app in payload.apps] == ["v1", "v2"]
    for app in payload.apps:
        assert [fn["id"] for fn in json.loads(app.functions)] == [
            f"{app.app_name}-alpha",
            f"{app.app_name}-zebra",
        ]

    original = _sync({"test": AppConfig(_configs(("alpha",)), "v1")})
    changed = _sync(
        {"test": AppConfig(_configs(("alpha",), event="demo/changed"), "v1")}
    )
    assert original.apps[0].functions != changed.apps[0].functions


@pytest.mark.parametrize("discovery", [False, True])
def test_fresh_processes_and_hash_seeds(discovery: bool) -> None:
    # Python Connect requires an explicit list. Model user-side automatic
    # discovery of function exports through an unordered, deduplicated inventory.
    program = textwrap.dedent(
        """
        import logging
        import sys
        import types
        import inngest
        from inngest._internal import comm_lib
        from inngest.connect._internal import connect_pb2
        from inngest.connect._internal.init_handshake_handler import _create_sync_message
        from inngest.connect._internal.models import AppConfig

        client = inngest.Inngest(
            app_id="test",
            is_production=False,
            logger=logging.getLogger("test"),
        )
        module = types.ModuleType("discovered_functions")
        names = ["function_" + str(i) for i in range(16)]
        async def handler(ctx):
            return "ok"
        for name in names:
            fn = client.create_function(
                fn_id=name,
                trigger=inngest.TriggerEvent(event="demo/event"),
            )(handler)
            setattr(module, name, fn)
        if sys.argv[1] == "True":
            names = {
                name for name in dir(module)
                if isinstance(getattr(module, name), inngest.Function)
            }
        functions = [getattr(module, name) for name in names]
        configs = comm_lib.get_function_configs(
            "wss://connect", {fn.id: fn for fn in functions}
        )
        assert not isinstance(configs, Exception)
        message = _create_sync_message(
            app_configs={"test": AppConfig(configs, "same-code")},
            auth_data=connect_pb2.AuthData(),
            connection_id="test",
            env=None,
            instance_id="test",
            max_worker_concurrency=None,
        )
        assert not isinstance(message, Exception)
        data = connect_pb2.WorkerConnectRequestData.FromString(message.payload)
        sys.stdout.buffer.write(data.apps[0].functions)
        """
    )
    payloads = {
        subprocess.check_output(
            [sys.executable, "-c", program, str(discovery)],
            env={**os.environ, "PYTHONHASHSEED": seed},
            timeout=15,
        )
        for seed in ("0", "1", "7", "42", "random")
    }
    assert len(payloads) == 1
    assert [fn["id"] for fn in json.loads(payloads.pop())] == sorted(
        f"test-function_{i}" for i in range(16)
    )
