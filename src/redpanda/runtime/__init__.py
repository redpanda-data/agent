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

import os

from redpanda.agents import Agent, SSEMCPEndpoint
from redpanda.runtime._grpc import RuntimeServer, serve_main


async def serve(agent: Agent) -> None:
    addr = os.getenv("REDPANDA_CONNECT_AGENT_RUNTIME_MCP_SERVER")
    if addr:
        agent.mcp.append(SSEMCPEndpoint(addr))
    server = RuntimeServer(agent)
    await serve_main(server)


__all__ = ["serve"]
