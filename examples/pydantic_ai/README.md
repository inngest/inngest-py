# Pydantic AI example

Example for how to automatically wrap Pydantic tools with Inngest steps.

## Initial setup

Create an `.env` file in the root of the repo with your `ANTHROPIC_API_KEY` env var.

Install dependencies by running `make install` from the root of the repo.

## Usage

Start the Dev Server by running `npx --ignore-scripts=false inngest-cli@latest dev --no-discovery --no-poll`.

Run the example by running `(cd examples/pydantic_ai && make dev)` from the root of the repo.

You should see output similar to this:

```
Rolling dice
The dice shows **5**!
```

And a function run in the Dev Server.
