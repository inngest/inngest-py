import asyncio
import tornado
from tornado.web import Application
import tornado.autoreload
from src.inngest import inngest_client
from examples.functions import functions
import inngest


async def main() -> None:
    app = Application()
    inngest.tornado.serve(app, inngest_client, functions)

    app.listen(8000)
    tornado.autoreload.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
