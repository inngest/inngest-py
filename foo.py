import asyncio


class Foo:
    async def bar(self) -> str:
        return "Hi"


def main():
    foo = Foo()
    print(foo.bar())


main()
# asyncio.run(main())

# async def async_func():
#     return "Hello from async function!"


# def sync_func():
#     foo = async_func()
#     foo = asyncio.run(foo)
#     print(1)
#     return foo


# print(sync_func())
