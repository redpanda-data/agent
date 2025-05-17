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

import asyncio
import base64
import json
import signal
from typing import override

import grpc  # pyright: ignore[reportMissingTypeStubs]
import grpc.aio  # pyright: ignore[reportMissingTypeStubs]
from grpc_health.v1 import health_pb2, health_pb2_grpc  # pyright: ignore[reportMissingTypeStubs]
from grpc_health.v1.health import HealthServicer  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry import trace
from opentelemetry.sdk import trace as tracesdk
from pydantic import BaseModel

from redpanda.agents import Agent
from redpanda.runtime.v1alpha1 import (
    agent_pb2 as pb,
    agent_pb2_grpc as grpcpb,
    message_pb2 as msg_pb,
)

from ._otel import convert_spans, current_spans_context_var


def _serialize_payload(payload: msg_pb.Value) -> str:
    kind = payload.WhichOneof("kind")
    if kind == "bool_value":
        return "true" if payload.bool_value else "false"
    elif kind == "bytes_value":
        return base64.standard_b64encode(payload.bytes_value).decode("hex")
    elif kind == "double_value":
        return str(payload.double_value)
    elif kind == "integer_value":
        return str(payload.integer_value)
    elif kind == "list_value":
        return (
            "[" + ",".join([_serialize_payload(item) for item in payload.list_value.values]) + "]"
        )
    elif kind == "null_value":
        return "null"
    elif kind == "string_value":
        return json.dumps(payload.string_value)
    elif kind == "struct_value":
        return (
            "{"
            + ",".join(
                [
                    json.dumps(k) + ":" + _serialize_payload(v)
                    for k, v in payload.struct_value.fields.items()
                ]
            )
            + "}"
        )
    elif kind == "timestamp_value":
        return json.dumps(payload.timestamp_value.ToJsonString())
    else:
        raise ValueError(f"Unknown payload kind: {kind}")


class RuntimeServer(grpcpb.AgentRuntimeServicer):
    agent: Agent
    tracer: trace.Tracer

    def __init__(self, agent: Agent, tracer: trace.Tracer):
        self.agent = agent
        self.tracer = tracer

    @override
    async def InvokeAgent(
        self,
        request: pb.InvokeAgentRequest,
        context: grpc.aio.ServicerContext[pb.InvokeAgentResponse, pb.InvokeAgentResponse],
    ) -> pb.InvokeAgentResponse:
        trace_ctx = None
        if request.HasField("trace_context"):
            span_context = trace.SpanContext(
                trace_id=int(request.trace_context.trace_id, 16),
                span_id=int(request.trace_context.span_id, 16),
                is_remote=True,
                trace_flags=trace.TraceFlags(int(request.trace_context.trace_flags, 16)),
            )
            trace_ctx = trace.set_span_in_context(trace.NonRecordingSpan(span_context))
        spans: list[tracesdk.ReadableSpan] = []
        token = current_spans_context_var.set(spans)
        try:
            payload: str
            if request.message.WhichOneof("payload") == "structured":
                payload = _serialize_payload(request.message.structured)
            else:
                payload = request.message.bytes.decode("utf-8")
            with self.tracer.start_as_current_span("agent_invoke", context=trace_ctx):
                output = await self.agent.run(input=payload)
            if isinstance(output, BaseModel):
                output = output.model_dump_json()
            elif not isinstance(output, str):
                output = json.dumps(output)
            return pb.InvokeAgentResponse(
                message=msg_pb.Message(
                    bytes=output.encode("utf-8"),
                    metadata=request.message.metadata,
                ),
                trace=pb.Trace(spans=convert_spans(spans)) if trace_ctx else None,
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise
        finally:
            current_spans_context_var.reset(token)


async def serve_main(runtime_server: RuntimeServer):
    health = HealthServicer()
    health.set(  # pyright: ignore[reportUnknownMemberType]
        "plugin",
        health_pb2.HealthCheckResponse.ServingStatus.Value("SERVING"),
    )
    server = grpc.aio.server()
    grpcpb.add_AgentRuntimeServicer_to_server(
        runtime_server,
        server,
    )
    health_pb2_grpc.add_HealthServicer_to_server(  # pyright: ignore[reportUnknownMemberType]
        health,
        server,
    )
    port = server.add_insecure_port("127.0.0.1:0")
    print(f"1|1|tcp|127.0.0.1:{port}|grpc", flush=True)
    await server.start()

    async def stop(sig: int):
        await server.stop(grace=None)
        loop.remove_signal_handler(sig)

    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda sig: asyncio.ensure_future(stop(sig)), sig)
        await server.wait_for_termination()
    finally:
        await server.stop(grace=None)
