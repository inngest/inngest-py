<div align="center">
  <br/>
    <a href="https://www.inngest.com"><img src="https://github.com/inngest/.github/raw/main/profile/github-readme-banner-2025-06-20.png"/></a>
  <br/>
  <br/>
  <p>
    Serverless event-driven queues, background jobs, and scheduled jobs for Python.<br />
    Add durable functions and workflows to any framework and platform.
  </p>
  Read the <a href="https://www.inngest.com/docs?ref=github-inngest-js-readme">documentation</a> and get started in minutes.
  <br/>
  <p>

[![pypi](https://img.shields.io/pypi/v/inngest.svg)](https://pypi.python.org/pypi/inngest)
![versions](https://img.shields.io/pypi/pyversions/inngest.svg)
[![discord](https://img.shields.io/discord/842170679536517141?label=discord)](https://www.inngest.com/discord)
[![twitter](https://img.shields.io/twitter/follow/inngest?style=social)](https://twitter.com/inngest)

  </p>
</div>

<hr />

# Inngest Python SDK

Inngest's SDK adds durable functions to Python in a few lines of code. Using this SDK, you can write
background jobs as step functions without new queueing infrastructure such as celery.

We currently support the following frameworks (but adding a new framework is easy!):

- DigitalOcean Functions
- Django (`>=5.0`)
- FastAPI (`>=0.110.0`)
- Flask (`>=3.0.0`)
- Tornado (`>=6.4`)

Python 3.10 is the minimum version we support.

## Getting started

[Quick start guide](https://www.inngest.com/docs/getting-started/quick-start/python)

## Examples

> 💡 You can mix `async` and non-`async` functions in the same app!

- [Basic](#basic-no-steps)
- [Step run](#step-run)
- [Async function](#async-function)

### Basic (no steps)

This is a minimal example of an Inngest function:

```py
import flask
import inngest.flask
import requests

inngest_client = inngest.Inngest(
    app_id="flask_example",
    is_production=False,
)

@inngest_client.create_function(
    fn_id="find_person",
    trigger=inngest.TriggerEvent(event="app/person.find"),
)
def fetch_person(ctx: inngest.ContextSync) -> dict:
    person_id = ctx.event.data["person_id"]
    res = requests.get(f"https://swapi.dev/api/people/{person_id}", verify=False)
    return res.json()

app = flask.Flask(__name__)

# Register functions with the Inngest server
inngest.flask.serve(
    app,
    inngest_client,
    [fetch_person],
)

app.run(port=8000)
```

[Each function is automatically backed by its own queue](https://www.inngest.com/docs/learn/how-functions-are-executed). Functions can contain steps, which act as code
level transactions. Each step retries on failure, and runs once on success. Function state is automatically managed.

Let's run the function. Send the following event in the [local development server (Dev Server UI)](https://www.inngest.com/docs/local-development) and the `fetch_person` function will run:

```json
{
  "name": "app/person.find",
  "data": {
    "person_id": 1
  }
}
```

### Step run

The following example registers a function that will:

1. Get the person ID from the event
1. Fetch the person with that ID
1. Fetch the person's ships
1. Return a summary dict

```py
@inngest_client.create_function(
    fn_id="find_ships",
    trigger=inngest.TriggerEvent(event="app/ships.find"),
)
def fetch_ships(ctx: inngest.ContextSync) -> dict:
    """
    Find all the ships a person has.
    """

    person_id = ctx.event.data["person_id"]

    def _fetch_person() -> dict:
        res = requests.get(f"https://swapi.dev/api/people/{person_id}", verify=False)
        return res.json()

    # Wrap the function with step.run to enable retries
    person = step.run("fetch_person", _fetch_person)

    def _fetch_ship(url: str) -> dict:
        res = requests.get(url)
        return res.json()

    ship_names = []
    for ship_url in person["starships"]:
        # step.run works in loops!
        ship = step.run("fetch_ship", _fetch_ship, ship_url)

        ship_names.append(ship["name"])

    return {
        "person_name": person["name"],
        "ship_names": ship_names,
    }
```

Send the following event in the Dev Server UI and the `fetch_person` function will run:

```json
{
  "name": "app/ships.find",
  "data": {
    "person_id": 1
  }
}
```

### Async function

```py
@inngest_client.create_function(
    fn_id="find_person",
    trigger=inngest.TriggerEvent(event="app/person.find"),
)
async def fetch_person(ctx: inngest.Context) -> dict:
    person_id = ctx.event.data["person_id"]
    async with httpx.AsyncClient(verify=False) as client:
        res = await client.get(f"https://swapi.dev/api/people/{person_id}")
        return res.json()
```

### Sending an event outside a function

Sometimes you want to send an event from a normal, non-Inngest function. You can do that using the client:

```py
inngest_client.send_sync(inngest.Event(name="app/test", data={"person_id": 1}))
```

If you prefer `async` then use the `send` method instead:

```py
await inngest_client.send(inngest.Event(name="app/test", data={"person_id": 1}))
```

## Using in production

The Dev Server is not used in production. [Inngest Cloud](https://app.inngest.com) is used instead.

The `INNGEST_EVENT_KEY` and `INNGEST_SIGNING_KEY` environment variables must be set. These secrets establish trust between Inngest Cloud and your app. We also use request signature verification to mitigate man-in-the-middle attacks. You can read more about [environment variables](https://www.inngest.com/docs/reference/python/overview/env-vars) in our docs.

Your Inngest client must be in production mode. This is typically done with an environment variable:

```py
inngest_client = inngest.Inngest(
    app_id="my_app",
    is_production=os.getenv("INNGEST_DEV") is None,
)
```
