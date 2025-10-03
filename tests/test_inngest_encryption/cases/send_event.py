"""
step.send_event properly encrypts the event data. The triggered function
receives decrypted data.
"""

import typing

import inngest
import nacl.hash
import nacl.secret
import test_core
from inngest._internal import server_lib
from inngest_encryption import EncryptionMiddleware

from . import base

_secret_key = "my-secret-key"


enc = base.Encryptor(
    nacl.hash.blake2b(
        _secret_key.encode("utf-8"),
        digest_size=nacl.secret.SecretBox.KEY_SIZE,
    )
)


class _State(base.BaseState):
    child_run_id: str | None = None
    child_event: inngest.Event | None = None

    async def wait_for_child_run_id(self) -> str:
        def assertion() -> None:
            assert self.child_run_id is not None

        await test_core.wait_for(assertion)
        assert self.child_run_id is not None
        return self.child_run_id


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    child_event_name = f"{event_name}/child"
    fn_id = base.create_fn_id(test_name)
    state = _State()
    mw = EncryptionMiddleware.factory(_secret_key)

    @client.create_function(
        fn_id=f"{fn_id}/child",
        middleware=[mw],
        retries=0,
        trigger=inngest.TriggerEvent(event=child_event_name),
    )
    def child_fn_sync(ctx: inngest.ContextSync) -> dict[str, str]:
        state.child_run_id = ctx.run_id
        state.child_event = ctx.event

        encrypted = ctx.event.data["encrypted"]
        assert isinstance(encrypted, dict)
        phone = encrypted["phone"]
        assert isinstance(phone, str)
        return {"msg": f"Number is {phone}"}

    @client.create_function(
        fn_id=fn_id,
        middleware=[mw],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        ctx.step.send_event(
            "send",
            inngest.Event(
                data={
                    "encrypted": {
                        "phone": "867-5309",
                    },
                    "user_id": "abc123",
                },
                name=child_event_name,
            ),
        )

    @client.create_function(
        fn_id=f"{fn_id}/child",
        middleware=[mw],
        retries=0,
        trigger=inngest.TriggerEvent(event=child_event_name),
    )
    async def child_fn_async(ctx: inngest.Context) -> dict[str, str]:
        state.child_run_id = ctx.run_id
        state.child_event = ctx.event

        encrypted = ctx.event.data["encrypted"]
        assert isinstance(encrypted, dict)
        phone = encrypted["phone"]
        assert isinstance(phone, str)
        return {"msg": f"Number is {phone}"}

    @client.create_function(
        fn_id=fn_id,
        middleware=[mw],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        await ctx.step.send_event(
            "send",
            inngest.Event(
                data={
                    "encrypted": {
                        "phone": "867-5309",
                    },
                    "user_id": "abc123",
                },
                name=child_event_name,
            ),
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        await test_core.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.RunStatus.COMPLETED,
        )

        child_run = await test_core.client.wait_for_run_status(
            await state.wait_for_child_run_id(),
            test_core.RunStatus.COMPLETED,
        )

        assert state.child_event is not None
        _assert_event_in_child_run(state.child_event)

        _assert_event_in_db(child_run.event)

    fn: list[inngest.Function[typing.Any]]
    if is_sync:
        fn = [child_fn_sync, fn_sync]
    else:
        fn = [child_fn_async, fn_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )


def _assert_event_in_child_run(event: inngest.Event) -> None:
    """
    Assert the event that the child run received. It should be decrypted.
    """

    assert event.data == {
        "encrypted": {
            "phone": "867-5309",
        },
        "user_id": "abc123",
    }


def _assert_event_in_db(event: inngest.Event) -> None:
    """
    Assert the event that's in the Dev Server's database. It should be
    encrypted.
    """

    assert sorted(event.data.keys()) == [
        "encrypted",
        "user_id",
    ]

    # The encrypted data schema is correct.
    encrypted = event.data["encrypted"]
    assert isinstance(encrypted, dict)
    assert sorted(encrypted.keys()) == [
        "__ENCRYPTED__",
        "__STRATEGY__",
        "data",
    ]
    assert encrypted["__ENCRYPTED__"] is True
    assert encrypted["__STRATEGY__"] == "inngest/libsodium"
    assert isinstance(encrypted["data"], str)

    # The encrypted data can be decrypted.
    assert enc.decrypt(encrypted["data"].encode("utf-8")) == {
        "phone": "867-5309",
    }
