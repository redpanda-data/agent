import asyncio
from pathlib import Path
from typing import Any, override

from agents import Agent, RPKMCPEndpoint
from agents.agent import AgentHooks
from agents.tools import Tool


class MyHooks(AgentHooks):
    @override
    async def on_start(self, agent: Agent) -> None:
        print("Agent started")

    @override
    async def on_end(self, agent: Agent, output: Any) -> None:
        print("Agent ended")

    @override
    async def on_tool_start(
        self,
        agent: Agent,
        tool: Tool,
        args: str,
    ) -> None:
        print(f"Agent calling tool {tool.name} with args: {args}")

    @override
    async def on_tool_end(
        self,
        agent: Agent,
        tool: Tool,
        result: str,
    ) -> None:
        print(f"Agent tool {tool.name} resulted in: {result}")


my_agent = Agent(
    name="ConnectPipelineDevAgent",
    model="openai/gpt-4o",
    instructions="""
    You are a development agent that helps an engineer create Redpanda Connect pipelines.
    Redpanda Connect is a stream processing tool that allows you to move data between different systems.
    Redpanda Connect pipelines are defined in a single YAML file usually called `connect.yaml`.
    You have access to the developer's project with filesystem access as well as a file to lint pipelines,
    which is usually a good idea to use after modifying the `connect.yaml` file.
    Additionally, you have access to another agent that has full access to the Redpanda documentation that
    can lookup functionality or how the project works in more depth. However, that agent is not specific
    for Redpanda Connect so make sure you provide it with context when asking it questions. Please feel free
    to ask multiple questions.

    Always write the output to the directory.

    NOTE: You really need to ask the documentation agent for help. Also there is no opportunity to ask the user
    for comfirmation.
    """.strip().replace("\n", ""),
    mcp=[
        RPKMCPEndpoint(directory=Path("mcp")),
    ],
    hooks=MyHooks(),
)


async def main() -> None:
    while True:
        try:
            prompt = input("> ")
        except EOFError:
            return
        response = await my_agent.run(input=prompt)
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
