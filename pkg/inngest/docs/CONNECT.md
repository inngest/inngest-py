# Connect

How the SDK connects to the Inngest server over a persistent WebSocket. This is an alternative to the HTTP-based `serve()` functions.

For lower-level details, see `./inngest/connect/docs/`.

## Why Connect?

In HTTP serve mode, the Inngest server sends requests to the SDK over HTTP. This requires the SDK to be publicly accessible and is subject to HTTP timeouts. Connect flips the direction: the SDK opens an outbound WebSocket to the Inngest server. This means:

- No need to expose your app to the internet.
- No HTTP request timeouts for long-running functions.
- Only works in long-lived processes (not serverless).

## Public API

```python
connection = inngest.connect([(client, [func1, func2])])
await connection.start()  # Blocks until the connection closes
```

The `connect()` function returns a `WorkerConnection`. Calling `start()` blocks the main thread until shutdown.
