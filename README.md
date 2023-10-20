# Inngest Python SDK

Supported features:

- ✅ `step.run`
- ✅ `step.send_event`
- ✅ `step.sleep_until`
- ✅ Config:
  - `retries`
- ✅ Frameworks:
  - Flask
- ✅ Registration

Unsupported features:

- 🚫 `step.sleep`
- 🚫 `step.wait_for_event`
- 🚫 Async/await syntax
- 🚫 Config:
  - `batch_events`
  - `cancel_on`
  - `concurrency`
  - `debounce`
  - `on_failure`
  - `rate_limit`
- 🚫 Frameworks:
  - Django
  - Tornado
  - FastAPI
- 🚫 Logger
- 🚫 Middleware
- 🚫 Parallel steps
- 🚫 Request signing and verification
