# Copyright 2025 Redpanda Data, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from contextlib import AsyncExitStack
from typing import Any, override

from litellm import (
    CustomStreamWrapper,
    acompletion,  # pyright: ignore[reportUnknownVariableType]
)
from litellm.types.utils import (  # pyright: ignore[reportMissingTypeStubs]
    ChatCompletionMessageToolCall,
    Message,
    StreamingChoices,
)
from pydantic import BaseModel

from ._mcp import MCPClient, MCPEndpoint, mcp_client
from ._tools import Tool, ToolResponse


class AgentHooks:
    """
    A class that receives callbacks on various lifecycle events for a specific agent.
    """

    async def on_start(
        self,
        agent: "Agent",
    ) -> None:
        """Called before the agent is invoked."""
        _ = agent

    async def on_end(
        self,
        agent: "Agent",
        output: Any,
    ) -> None:
        """Called when the agent produces a final output."""
        _ = agent, output

    async def on_tool_start(
        self,
        agent: "Agent",
        tool: Tool,
        args: str,
    ) -> None:
        """Called before a tool is invoked."""
        _ = agent, tool, args

    async def on_tool_end(
        self,
        agent: "Agent",
        tool: Tool,
        result: str,
    ) -> None:
        """Called after a tool is invoked."""
        _ = agent, tool, result


class Agent:
    """
    An agent is a wrapper around a LLM model that can generate responses to input text.

    Attributes:
        name: The name of the agent.
        model: The LLM model that the agent will use. Models follow the format of
            "<provider>/<model>" and are loaded using [litellm](https://docs.litellm.ai/docs/providers).
            Examples:
                "openai/gpt-4o"
                "gemini/gemini-pro"
                "bedrock/bedrock-claude-v1"
        response_format: The Pydantic model that the response will be validated against.
        parameters: A dictionary of parameters that the model will use.
            These parameters are specific to the model.
            Examples:
                {"temperature": 0.5}
                {"max_tokens": 100}
                {"temperature": 0.5, "max_tokens": 100}
        tools: The tools exposed to the agent.
        mcp: The MCP endpoints that the agent can invoke.
        hooks: Callbacks to invoke during various points of the agent runtime.
    """

    name: str
    model: str
    instructions: str | None
    response_format: type[BaseModel] | None
    parameters: dict[str, Any]
    tools: list[Tool]
    mcp: list[MCPEndpoint]
    hooks: AgentHooks

    def __init__(
        self,
        name: str,
        model: str,
        instructions: str | None = None,
        response_type: type[BaseModel] | None = None,
        tools: list[Tool] | None = None,
        mcp: list[MCPEndpoint] | None = None,
        hooks: AgentHooks | None = None,
        **kwargs: Any,
    ):
        """
        Args:
            name: The name of the agent.
            model: The LLM model that the agent will use. Models follow the format of
                "<provider>/<model>" and are loaded using [litellm](https://docs.litellm.ai/docs/providers).
                Examples:
                    "openai/gpt-4o"
                    "gemini/gemini-pro"
                    "bedrock/bedrock-claude-v1"
            instructions: The system prompt for the agent.
            response_type: The Pydantic model that the response will be validated against.
                If None, the response will be a string.
            tools: The tools exposed to the agent.
            mcp: The MCP endpoints that the agent can invoke.
            hooks: Callbacks to invoke during various points of the agent runtime.
            **kwargs: A dictionary of parameters that the model will use.
                These parameters are specific to the model.
                Examples:
                    {"temperature": 0.5}
                    {"max_tokens": 100}
                    {"temperature": 0.5, "max_tokens": 100}
        """
        self.name = name
        self.model = model
        self.instructions = instructions
        self.response_format = response_type
        self.parameters = kwargs
        self.tools = tools or []
        self.mcp = mcp or []
        self.hooks = hooks or AgentHooks()

    async def run(self, input: str) -> Any:
        """
        Generate a response from the model given an input text.

        Args:
            input: The input text that the model will use to generate a response.
        Returns:
            The generated response from the model.
        """
        await self.hooks.on_start(self)
        async with AsyncExitStack() as stack:
            mcp_clients: list[MCPClient] = []
            for server in self.mcp:
                mcp_clients.append(await stack.enter_async_context(mcp_client(server)))

            tools = {tool.name: tool for tool in self.tools}

            for client in mcp_clients:
                await client.initialize()
                for tool in await client.list_tools():
                    if tool.name not in tools:
                        tools[tool.name] = tool
                    else:
                        # TODO: Warn on conflicting tools?
                        pass

            tool_defs = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools.values()
            ]
            messages: list[dict[str, str] | Message] = [{"role": "user", "content": input}]
            if self.instructions:
                messages = [{"role": "system", "content": self.instructions}] + messages
            while True:
                model_resp = await acompletion(
                    model=self.model,
                    response_format=self.response_format,
                    messages=messages,
                    tools=tool_defs,
                    **self.parameters,
                )
                if isinstance(model_resp, CustomStreamWrapper):
                    raise Exception("unexpected response type of CustomStreamWrapper")
                choice_resp = model_resp.choices[-1]
                if isinstance(choice_resp, StreamingChoices):
                    raise Exception("unexpected streaming response type")
                if choice_resp.message.tool_calls:
                    messages.append(choice_resp.message)
                    messages.extend(await self._call_tools(choice_resp.message.tool_calls, tools))
                    continue
                output = choice_resp.message.content
                if output is None:
                    raise Exception("unexpected response type of None")
                if self.response_format is not None:
                    output = self.response_format.model_validate_json(output)
                await self.hooks.on_end(self, output)
                return output

    async def _call_tools(
        self, tool_calls: list[ChatCompletionMessageToolCall], tools: dict[str, Tool]
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            func = tool_call.function
            selected = func.name and tools.get(func.name)
            if not selected:
                raise Exception(f"tool {func.name} not found")
            await self.hooks.on_tool_start(self, selected, func.arguments)
            resp = await selected(json.loads(func.arguments))
            if isinstance(resp, ToolResponse):
                output: Any = []
                for content in resp.content:
                    if content.type == "text":
                        output.append(
                            {
                                "type": "text",
                                "text": content.data,
                            }
                        )
                    elif content.type == "image":
                        output.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content.mime_type};base64,{content.data}",
                                },
                            }
                        )
                    else:
                        raise NotImplementedError(f"Unknown content type: {content.type}")
            if isinstance(resp, BaseModel):
                output = resp.model_dump_json()
            else:
                output = json.dumps(resp)
            await self.hooks.on_tool_end(
                self, selected, output if isinstance(output, str) else json.dumps(output)
            )
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": selected.name,
                    "content": output,
                }
            )
        return messages

    def as_tool(self) -> Tool:
        # TODO(rockwood): support handoffs and passing more context
        return AgentTool(self)


class AgentTool(Tool):
    """
    A tool that wraps an agent and allows it to be called another agent.
    """

    agent: Agent
    """
    The agent that this tool will call.
    """

    class Input(BaseModel):
        input: str

    def __init__(self, agent: Agent):
        super().__init__(
            name=agent.name,
            description=f"An agent called {agent.name} you can pass text to and get a response.",
            parameters=AgentTool.Input.model_json_schema(),
        )
        self.agent = agent

    @override
    async def __call__(self, args: dict[str, Any]) -> Any:
        return await self.agent.run(args["input"])
