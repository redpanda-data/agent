import asyncio

import redpanda.runtime
from redpanda.agents import Agent

my_agent = Agent(
    name="WeatherAgent",
    model="openai/gpt-4o",
    instructions="""
    You are a helpful AI agent for finding out about the weather.
    """.strip(),
)

asyncio.run(redpanda.runtime.serve(my_agent))
