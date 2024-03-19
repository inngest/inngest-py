import inngest


def create_async_functions(client: inngest.Inngest) -> list[inngest.Function]:
    @client.create_function(
        fn_id="invokee",
        retries=0,
        trigger=inngest.TriggerEvent(event="app/dummy"),
    )
    async def invokee(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> str:
        raise Exception("oh no")

    @client.create_function(
        fn_id="invoker",
        trigger=inngest.TriggerEvent(event="app/invoke"),
    )
    async def invoker(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        res = await step.invoke_by_id(
            "invoke",
            app_id=client.app_id,
            function_id="invokee",
        )
        print(res)

    return [invokee, invoker]


def create_sync_functions(client: inngest.Inngest) -> list[inngest.Function]:
    @client.create_function(
        fn_id="invokee",
        retries=0,
        trigger=inngest.TriggerEvent(event="app/dummy"),
    )
    def invokee(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        raise Exception("oh no")
        return "Hello from invokee"

    @client.create_function(
        fn_id="invoker",
        trigger=inngest.TriggerEvent(event="app/invoke"),
    )
    def invoker(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        res = step.invoke_by_id(
            "invoke",
            app_id=client.app_id,
            function_id="invokee",
        )
        print(type(res))
        print(res)

    return [invokee, invoker]
