# Inngest Python SDK: Remote state

This package provides the tools for storing step output in a custom store (e.g. AWS S3). This can drastically reduce bandwidth to/from the Inngest server, since step output is stored within your infrastructure rather than Inngest's.

## Usage

Setting remote state middleware on the client will turn on remote state for steps in all functions:

```py
import inngest
from inngest_remote_state import RemoteStateMiddleware
from inngest_remote_state.s3 import S3Driver

inngest.Inngest(
    app_id="my-app",
    middleware=[
        RemoteStateMiddleware.factory(
            S3Driver(
                bucket="inngest-remote-state",
                client=boto3.client("s3"),
            )
        )
    ],
)
```

The entire `step.run` output is stored in the remote store:

```py
def _my_step() -> dict[str, object]:
    # Stored in the remote store.
    return {"msg": "hello"}

output = await step.run("my-step", _my_step)

# Available within this function (it's automatically loaded by the middleware).
print(output)
```
