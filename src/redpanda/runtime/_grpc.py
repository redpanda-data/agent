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
from pydantic import BaseModel

from redpanda.agents import Agent
from redpanda.runtime.proto import runtime_pb2 as pb, runtime_pb2_grpc as grpcpb


def _serialize_payload(payload: pb.Value) -> str:
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


class RuntimeServer(grpcpb.RuntimeServicer):
    agent: Agent

    def __init__(self, agent: Agent):
        self.agent = agent

    @override
    async def InvokeAgent(
        self,
        request: pb.InvokeAgentRequest,
        context: grpc.aio.ServicerContext[pb.InvokeAgentResponse, pb.InvokeAgentResponse],
    ) -> pb.InvokeAgentResponse:
        try:
            payload: str
            if request.message.WhichOneof("payload") == "structured":
                payload = _serialize_payload(request.message.structured)
            else:
                payload = request.message.serialized.decode("utf-8")
            output = await self.agent.run(input=payload)
            if isinstance(output, BaseModel):
                output = output.model_dump_json()
            elif not isinstance(output, str):
                output = json.dumps(output)
            return pb.InvokeAgentResponse(
                message=pb.Message(
                    serialized=output.encode("utf-8"),
                    metadata=request.message.metadata,
                ),
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise


async def serve_main(runtime_server: RuntimeServer):
    health = HealthServicer()
    health.set(  # pyright: ignore[reportUnknownMemberType]
        "plugin",
        health_pb2.HealthCheckResponse.ServingStatus.Value("SERVING"),
    )
    server = grpc.aio.server()
    grpcpb.add_RuntimeServicer_to_server(
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
