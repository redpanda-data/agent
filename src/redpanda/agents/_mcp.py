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

from contextlib import asynccontextmanager
from opentelemetry import trace
from typing import Any, override
import json

from mcp import ClientSession, Tool as MCPToolDef
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.websocket import websocket_client
from mcp.shared.exceptions import McpError

from ._tools import Tool, ToolResponse, ToolResponseImageContent, ToolResponseTextContent


class MCPEndpoint:
    """
    An Base class for all endpoints (ways to connect) to MCP servers.
    """

    # TODO(rockwood): support list change notifications
    _cache_enabled: bool
    _cached_tool_list: list[MCPToolDef] | None = None

    def __init__(self, cache_enabled: bool) -> None:
        self._cache_enabled = cache_enabled


class StdioMCPEndpoint(MCPEndpoint):
    """
    A MCP endpoint that invokes a local process and communicates over stdin/stdout.
    """

    params: StdioServerParameters

    def __init__(self, params: StdioServerParameters, cache_enabled: bool = True):
        """
        Create a new StdioMCPEndpoint instance.

        Args:
            params: The parameters for the server.
            cache_enabled: Whether to cache the list of {tools,resources,prompts} from the server.
        """
        super().__init__(cache_enabled)
        self.params = params


class SSEMCPEndpoint(MCPEndpoint):
    """
    A MCP endpoint that communicates with an MCP server over Server-Sent Events.
    """

    url: str

    def __init__(self, url: str, cache_enabled: bool = True):
        """
        Create a new SSEMCPEndpoint instance.

        Args:
            url: The URL of the SSE server.
            cache_enabled: Whether to cache the list of {tools,resources,prompts} from the server.
        """
        super().__init__(cache_enabled)
        self.url = url

    @property
    def headers(self) -> dict[str, Any]:
        return {}


class WebsocketMCPEndpoint(MCPEndpoint):
    """
    A MCP endpoint that communicates with an MCP server over a WebSocket.
    """

    url: str

    def __init__(self, url: str, cache_enabled: bool = True):
        """
        Create a new WebsocketMCPEndpoint instance.

        Args:
            url: The URL of the WebSocket server.
            cache_enabled: Whether to cache the list of {tools,resources,prompts} from the server.
        """
        super().__init__(cache_enabled)
        self.url = url


@asynccontextmanager
async def mcp_client(server: MCPEndpoint):
    """
    Create a new MCP client for the given server.
    """
    if isinstance(server, StdioMCPEndpoint):
        async with stdio_client(server.params) as (read, write):
            async with ClientSession(read, write) as client:
                yield MCPClient(server, client)
    elif isinstance(server, SSEMCPEndpoint):
        async with sse_client(server.url, server.headers) as (read, write):
            async with ClientSession(read, write) as client:
                yield MCPClient(server, client)
    elif isinstance(server, WebsocketMCPEndpoint):
        async with websocket_client(server.url) as (read, write):
            async with ClientSession(read, write) as client:
                yield MCPClient(server, client)
    else:
        raise NotImplementedError(f"Unknown server type: {server}")


class MCPClient:
    """
    A wrapper around an MCP client session.
    """

    _server: MCPEndpoint
    _session: ClientSession

    def __init__(self, server: MCPEndpoint, session: ClientSession):
        self._server = server
        self._session = session

    async def initialize(self):
        await self._session.initialize()

    async def list_tools(self) -> list[Tool]:
        if self._server._cache_enabled and self._server._cached_tool_list:
            return [MCPTool(self, t) for t in self._server._cached_tool_list]
        try:
            result = await self._session.list_tools()
        except McpError as e:
            if e.error.message == "tools not supported":
                return []
            raise
        tools = result.tools
        if self._server._cache_enabled:
            self._server._cached_tool_list = tools
        return [MCPTool(self, t) for t in tools]

    async def call_tool(self, tool: str, args: dict[str, Any]) -> Any:
        result = await self._session.call_tool(tool, args)
        if result.isError:
            raise Exception(f"error invoking tool {tool}")
        # TODO: get this into a better format
        resp = ToolResponse()
        for content in result.content:
            if content.type == "text":
                resp.content.append(ToolResponseTextContent(data=content.text))
            elif content.type == "image":
                resp.content.append(
                    ToolResponseImageContent(mime_type=content.mimeType, data=content.data)
                )
            else:
                raise NotImplementedError(f"Unknown content type: {content.type}")
        return resp


class MCPTool(Tool):
    """
    A wrapper around an MCP server's tool call.
    """

    _client: MCPClient

    def __init__(self, client: MCPClient, tool_def: MCPToolDef):
        """
        Create a new MCPTool instance from an MCPClient and one of it's tools.
        """
        super().__init__(tool_def.name, tool_def.description, tool_def.inputSchema)
        self._client = client

    @override
    async def __call__(self, args: dict[str, Any]) -> Any:
        with trace.get_tracer("redpanda.agents").start_as_current_span("tool_call") as span:
            span.set_attribute("name", self.name)
            span.set_attribute("arguments", json.dumps(args))
            return await self._client.call_tool(self.name, args)
