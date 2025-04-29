import asyncio
from enum import Enum

from pydantic import BaseModel

import redpanda.runtime
from redpanda.agents import Agent


class Status(Enum):
    green = "green"
    yellow = "yellow"
    red = "red"


class Output(BaseModel):
    summary: str
    status: Status


redleader = Agent(
    name="Redleader",
    model="openai/gpt-4.1-mini",
    response_type=Output,
    instructions="""
    You are an internal Agent for the Redpanda Organization.
    Your job is to analyze the status of various projects and provide a summary of its current state.
    You have access to internal Google Drive where the status of various projects are stored.
    """.strip(),
)

asyncio.run(redpanda.runtime.serve(redleader))
