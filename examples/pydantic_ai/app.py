# ruff: noqa: S311

from __future__ import annotations

import asyncio
import logging
import random

import inngest
import pydantic_ai
import structlog
from inngest.connect import ConnectionState, connect
from inngest.experimental.pydantic_ai import InngestAgent, Serializer

# Change log level to hide verbose debug logs
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Pydantic AI stuff (non-Inngest-specific)

agent = pydantic_ai.Agent(
    "anthropic:claude-sonnet-4-5",
    name="dice-game",
    system_prompt=(
        "You're a dice game, you should roll the die and see if the number "
        "you get back matches the user's guess. If so, tell them they're a winner"
    ),
)


@agent.tool_plain
def roll_dice() -> str:
    print("Rolling dice")
    return str(random.randint(1, 6))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Inngest-specific stuff

inngest_client = inngest.Inngest(
    app_id="pydantic_ai_example",
    logger=structlog.get_logger(),
    serializer=Serializer(),
)

inngest_agent = InngestAgent(inngest_client, agent)

# Start an Inngest worker using Inngest Connect. This also works with Inngest's
# "serve" method, but Connect is cleaner for an ephemeral script like this
inngest_worker = connect([(inngest_client, [inngest_agent.fn])])


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Main


async def run_agent() -> None:
    await inngest_worker.wait_for_state(ConnectionState.ACTIVE)

    user_prompt = "My guess is 4"

    # Trigger the workflow and wait for its result
    result = await inngest_agent.run(user_prompt=user_prompt)
    print(result.output)

    # Shutdown the Inngest worker
    await inngest_worker.close()


async def main() -> None:
    await asyncio.gather(inngest_worker.start(), run_agent())


asyncio.run(main())
