import importlib.metadata
import typing

VERSION: typing.Final = importlib.metadata.version("inngest_langchain")

# Marks the steps and spans this package runs for the user, so the Inngest UI
# can de-emphasize them.
ORIGIN: typing.Final = f"inngest-langchain@{VERSION}"
