# Inngest Python SDK: Encryption

This package provides encryption for the Inngest Python SDK.

## Usage

Setting encryption middleware on the client will turn on encryption for events and steps in all functions:

```py
import inngest
from inngest_encryption import EncryptionMiddleware

inngest.Inngest(
    name="my-app",
    encryption_key="my-encryption-key",
    middleware=[EncryptionMiddleware.factory("my-secret-key")],
)
```

When sending events or invoking functions, only the `encrypted` field will be encrypted:

```py
await step.send_event(
    "my-step",
    inngest.Event(
        data={
            # Everything in this field will be encrypted.
            "encrypted": {
                "phone": "867-5309",
            },

            # Not encrypted.
            "user_id": "abc123",
        },
        name="my-event",
    ),
)

await step.invoke(
    "invoke",
    function=child_fn_async,
    data={
        # Everything in this field will be encrypted.
        "encrypted": {
            "phone": "867-5309",
        },

        # Not encrypted.
        "user_id": "abc123",
    },
)
```

> [!NOTE]  
> Only a portion of the event data is encrypted because that allows for control flow settings (e.g. concurrency key) to work. Since the Inngest server receives encrypted data, it can't perform control flow on values that are encrypted.

The entire `step.run` output is encrypted:

```py
def _my_step() -> dict[str, object]:
    # Encrypted when sending back to the Inngest server.
    return {"msg": "hello"}

output = await step.run("my-step", _my_step)

# Decrypted within this function.
print(output)
```

## Key rotation

When rotating the encryption key, you may still have active functions runs whose data is encrypted with the old key. To decrypt these, you can use the `fallback_decryption_keys` option:

```py
inngest.Inngest(
    name="my-app",
    encryption_key="my-encryption-key",
    middleware=[
        EncryptionMiddleware.factory(
            "new-secret-key",
            fallback_decryption_keys=["old-secret-key"],
        ),
    ],
)
```

If decryption fails with the new key, the encryption middleware will fall back to the old key.
