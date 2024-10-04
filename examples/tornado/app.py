import asyncio

import tornado
import tornado.autoreload
import tornado.web
from src.inngest.client import inngest_client
from src.inngest.functions import hello

import inngest.tornado


async def main() -> None:
    app = tornado.web.Application()
    inngest.tornado.serve(
        app,
        inngest_client,
        [hello],
    )

    app.listen(8000)
    tornado.autoreload.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
