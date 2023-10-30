import asyncio

import src.inngest
import tornado
import tornado.autoreload
import tornado.web

import examples.functions
import inngest.tornado


async def main() -> None:
    app = tornado.web.Application()
    inngest.tornado.serve(
        app,
        src.inngest.inngest_client,
        examples.functions.functions_sync,
    )

    app.listen(8000)
    tornado.autoreload.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
