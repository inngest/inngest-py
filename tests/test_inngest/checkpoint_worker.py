"""Disposable subprocess for checkpoint crash/restart integration tests."""

import argparse
import os
import pathlib

import fastapi
import httpx
import inngest
import inngest.fast_api
import uvicorn
from inngest._internal import net


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--directory", type=pathlib.Path, required=True)
    parser.add_argument("--crash", choices=["before", "after"], required=True)
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    marker = args.directory / "crashed"
    forward = httpx.Client(timeout=5)

    def transport(req: httpx.Request) -> httpx.Response:
        if "/checkpoint/" in req.url.path and not marker.exists():
            if args.crash == "after":
                res = forward.send(req)
                if res.status_code != 200:
                    return res
            marker.write_text("crashed", encoding="utf-8")
            os._exit(23)  # Deliberately simulate abrupt worker loss.
        return forward.send(req)

    client = inngest.Inngest(
        app_id=args.name,
        is_production=False,
        checkpointing=True,
        api_base_url=args.origin,
        event_api_base_url=args.origin,
    )
    client._http_client._http_client_sync = httpx.Client(
        transport=httpx.MockTransport(transport)
    )
    client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
        transport=httpx.MockTransport(transport)
    ).initialize()

    def effect(key: str, run_id: str) -> str:
        with (args.directory / "effects").open("a", encoding="utf-8") as f:
            f.write(key + "\n")
        (args.directory / "run-id").write_text(run_id, encoding="utf-8")
        return key

    def sync_fn(ctx: inngest.ContextSync) -> list[str]:
        a = ctx.step.run("a", effect, "a", ctx.run_id)
        b = ctx.step.run("b", effect, "b", ctx.run_id)
        return [a, b]

    async def async_fn(ctx: inngest.Context) -> list[str]:
        async def callback(key: str) -> str:
            return effect(key, ctx.run_id)

        a = await ctx.step.run("a", callback, "a")
        b = await ctx.step.run("b", callback, "b")
        return [a, b]

    fn = client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event=args.name), retries=3
    )(sync_fn if args.sync else async_fn)
    app = fastapi.FastAPI()
    inngest.fast_api.serve(app, client, [fn])
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="error")


if __name__ == "__main__":
    main()
