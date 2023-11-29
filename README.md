<div align="center">
  <br/>
    <a href="https://www.inngest.com"><img src="https://user-images.githubusercontent.com/306177/191580717-1f563f4c-31e3-4aa0-848c-5ddc97808a9a.png" width="250" /></a>
  <br/>
  <br/>
  <p>
    Serverless event-driven queues, background jobs, and scheduled jobs for Python.<br />
    Works with any framework and platform.
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

> 🚧 Currently in beta! It hasn't been battle-tested in production environments yet.

We currently support the following frameworks (but adding a new framework is easy!):

- Django
- FastAPI
- Flask
- Tornado

## Getting started

Install `inngest` in your project:

```sh
pip install inngest
```

Write a basic function and serve it (see the [basic](#basic-no-steps) example for guidance).

Start the Dev Server (the local version of our cloud platform):

```sh
npx inngest-cli@latest dev
```

Browse to http://127.0.0.1:8288 and you should see your app! Visit our docs to read more about the [Dev Server](https://www.inngest.com/docs/local-development).

## Examples

> 💡 You can mix `async` and non-`async` functions in the same app!

- [Basic](#basic-no-steps)
- [Step run](#step-run)
- [Async function](#async-function)

### Basic (no steps)

This is a minimal example of an Inngest function. It's missing some of our features but it's a good starting point.

```py
import flask
import inngest.flask
import requests

@inngest.create_function(
    fn_id="find_person",
    trigger=inngest.TriggerEvent(event="app/person.find"),
)
def fetch_person(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> dict:
    person_id = ctx.event.data["person_id"]
    res = requests.get(f"https://swapi.dev/api/people/{person_id}")
    return res.json()

app = flask.Flask(__name__)
inngest_client = inngest.Inngest(app_id="flask_example")

# Register functions with the Inngest server
inngest.flask.serve(
    app,
    inngest_client,
    [fetch_person],
)

app.run(port=8000)
```

### Step run

The following example registers a function that will:

1. Get the person ID from the event
1. Fetch the person with that ID
1. Fetch the person's ships
1. Return a summary dict

```py
@inngest.create_function(
    fn_id="find_ships",
    trigger=inngest.TriggerEvent(event="app/ships.find"),
)
def fetch_ships(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> dict:
    """
    Find all the ships a person has.
    """

    person_id = ctx.event.data["person_id"]

    def _fetch_person() -> dict:
        res = requests.get(f"https://swapi.dev/api/people/{person_id}")
        return res.json()

    # Wrap the function with step.run to enable retries
    person = step.run("fetch_person", _fetch_person)

    def _fetch_ship(url: str) -> dict:
        res = requests.get(url)
        return res.json()

    ship_names = []
    for ship_url in person["starships"]:
        # step.run works in loops!
        ship = step.run("fetch_ship", lambda: _fetch_ship(ship_url))

        ship_names.append(ship["name"])

    return {
        "person_name": person["name"],
        "ship_names": ship_names,
    }
```

### Async function

```py
@inngest.create_function(
    fn_id="find_person",
    trigger=inngest.TriggerEvent(event="app/person.find"),
)
async def fetch_person(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    person_id = ctx.event.data["person_id"]
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://swapi.dev/api/people/{person_id}")
        return res.json()
```

### Sending an event outside a function

Sometimes you want to send an event from a normal, non-Inngest function. You can do that using the client:

```py
import inngest.flask

inngest_client = inngest.Inngest(app_id="flask_example")
inngest_client.send_sync(inngest.Event(name="app/test", data={"person_id": 1}))
```

If you prefer `async` then use the `send` method instead:

```py
import asyncio
import inngest.flask

inngest_client = inngest.Inngest(app_id="flask_example")

async def main():
    await inngest_client.send(inngest.Event(name="app/test", data={"person_id": 1}))

asyncio.run(main())
```
