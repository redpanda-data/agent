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
from typing import Any, final, override

from opentelemetry import trace
from opentelemetry.sdk import trace as tracesdk
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from redpanda.agents import Agent, SSEMCPEndpoint

from ._grpc import RuntimeServer, serve_main
from ._otel import PassthroughTraceCollector


@final
class _TracingSSEMCPEndpoint(SSEMCPEndpoint):
    _propagator = TraceContextTextMapPropagator()

    @property
    @override
    def headers(self) -> dict[str, Any]:
        headers: dict[str, Any] = {}
        self._propagator.inject(headers)
        return headers


async def serve(agent: Agent) -> None:
    """
    Serve an agent as a Redpanda Connect processor plugin.

    This method runs for the entire lifetime of the server.

    Args:
        agent: The agent to serve.
    """
    provider = tracesdk.TracerProvider()
    trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(PassthroughTraceCollector()))
    addr = os.getenv("REDPANDA_CONNECT_AGENT_RUNTIME_MCP_SERVER")
    if addr:
        agent.mcp.append(_TracingSSEMCPEndpoint(addr))
    server = RuntimeServer(agent, trace.get_tracer("redpanda.runtime"))
    await serve_main(server)


__all__ = ["serve"]
