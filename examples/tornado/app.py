import asyncio

import tornado
import tornado.autoreload
import tornado.web
from src.inngest import inngest_client

import inngest.tornado
from examples import functions


async def main() -> None:
    app = tornado.web.Application()
    inngest.tornado.serve(
        app,
        inngest_client,
        functions.create_sync_functions(inngest_client),
    )

    app.listen(8000)
    tornado.autoreload.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
