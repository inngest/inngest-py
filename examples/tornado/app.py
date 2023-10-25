import asyncio

import tornado
import tornado.autoreload
from src.inngest import inngest_client
from tornado.web import Application

import inngest.tornado
from examples.functions import functions


async def main() -> None:
    app = Application()
    inngest.tornado.serve(app, inngest_client, functions)

    app.listen(8000)
    tornado.autoreload.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
