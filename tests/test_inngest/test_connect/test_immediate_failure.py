import inngest
from inngest.connect import connect

from .base import BaseTest


class TestImmediateFailure(BaseTest):
    """
    These tests check that the connect function immediately raises an error under
    certain conditions.
    """

    async def test_no_apps(self) -> None:
        with self.assertRaises(Exception) as e:
            connect([])

        assert str(e.exception) == "no apps provided"

    async def test_inconsistent_api_origin(self) -> None:
        client_1 = inngest.Inngest(
            api_base_url="https://api-1.inngest.com",
            app_id="app-1",
            is_production=False,
        )

        @client_1.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_1(ctx: inngest.Context) -> None:
            pass

        client_2 = inngest.Inngest(
            api_base_url="https://api-2.inngest.com",
            app_id="app-2",
            is_production=False,
        )

        @client_2.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_2(ctx: inngest.Context) -> None:
            pass

        with self.assertRaises(Exception) as e:
            connect(
                [
                    (client_1, [fn_1]),
                    (client_2, [fn_2]),
                ]
            )

        assert str(e.exception) == "inconsistent app config: API base URL"

    async def test_inconsistent_env(self) -> None:
        client_1 = inngest.Inngest(
            app_id="app-1",
            env="my-env-1",
            is_production=False,
        )

        @client_1.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_1(ctx: inngest.Context) -> None:
            pass

        client_2 = inngest.Inngest(
            app_id="app-2",
            env="my-env-2",
            is_production=False,
        )

        @client_2.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_2(ctx: inngest.Context) -> None:
            pass

        with self.assertRaises(Exception) as e:
            connect(
                [
                    (client_1, [fn_1]),
                    (client_2, [fn_2]),
                ]
            )

        assert str(e.exception) == "inconsistent app config: env"

    async def test_inconsistent_mode(self) -> None:
        client_1 = inngest.Inngest(app_id="app-1", signing_key="deadbeef")

        @client_1.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_1(ctx: inngest.Context) -> None:
            pass

        client_2 = inngest.Inngest(
            api_base_url="https://api.inngest.com/",
            app_id="app-2",
            is_production=False,
        )

        @client_2.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_2(ctx: inngest.Context) -> None:
            pass

        with self.assertRaises(Exception) as e:
            connect(
                [
                    (client_1, [fn_1]),
                    (client_2, [fn_2]),
                ]
            )

        assert str(e.exception) == "inconsistent app config: mode"

    async def test_inconsistent_signing_key(self) -> None:
        client_1 = inngest.Inngest(app_id="app-1", signing_key="deadbeef")

        @client_1.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_1(ctx: inngest.Context) -> None:
            pass

        client_2 = inngest.Inngest(app_id="app-2", signing_key="abc123")

        @client_2.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn_2(ctx: inngest.Context) -> None:
            pass

        with self.assertRaises(Exception) as e:
            connect(
                [
                    (client_1, [fn_1]),
                    (client_2, [fn_2]),
                ]
            )

        assert str(e.exception) == "inconsistent app config: signing key"
