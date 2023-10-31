# Inngest Python SDK

## 🚧 Currently in Alpha! Not guaranteed to be production ready! 🚧

Supported frameworks:

- Fast API
- Flask
- Tornado

## Examples

### Basic

This is a minimal example of an Inngest function. It's missing some of our features but it's a good starting point.

```py
import flask
import inngest.flask
import requests


@inngest.create_function_sync(
    fn_id="find_person",
    trigger=inngest.TriggerEvent(event="app/person.find"),
)
def fetch_person(
    *,
    event: inngest.Event,
    step: inngest.StepSync,
    **_kwargs: object,
) -> dict:
    person_id = event.data["person_id"]
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

### Steps

The following example registers a function that will:

1. Get the person ID from the event
1. Fetch the person with that ID
1. Fetch the person's ships
1. Return a summary dict

```py
import flask
import inngest.flask
import requests


@inngest.create_function_sync(
    fn_id="find_ships",
    trigger=inngest.TriggerEvent(event="app/ships.find"),
)
def fetch_ships(
    *,
    event: inngest.Event,
    step: inngest.StepSync,
    **_kwargs: object,
) -> dict:
    """
    Find all the ships a person has.
    """

    person_id = event.data["person_id"]

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


app = flask.Flask(__name__)

inngest_client = inngest.Inngest(app_id="flask_example")

# Register functions with the Inngest server
inngest.flask.serve(
    app,
    inngest_client,
    [fetch_ships],
)

app.run(port=8000)
```
