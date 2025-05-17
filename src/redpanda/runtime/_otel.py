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

import contextvars
import json
from collections.abc import Sequence
from typing import override

from google.protobuf.timestamp_pb2 import Timestamp as PbTimestamp
from opentelemetry import trace
from opentelemetry.sdk import trace as tracesdk
from opentelemetry.sdk.trace import export as traceexport
from opentelemetry.util import types as oteltypes

from redpanda.runtime.v1alpha1 import agent_pb2 as pb, message_pb2 as msg_pb


def _proto_timestamp_from_time_ns(time_ns: int | None) -> PbTimestamp:
    ts = PbTimestamp()
    if time_ns is not None:
        ts.FromNanoseconds(time_ns)
    return ts


def _convert_span_attributes(attrs: oteltypes.Attributes) -> dict[str, msg_pb.Value]:
    if attrs is None:
        return {}
    pb_attrs: dict[str, msg_pb.Value] = {}
    for k, v in attrs.items():
        pb_v = msg_pb.Value()
        if isinstance(v, str):
            pb_v.string_value = v
        elif isinstance(v, bool):
            pb_v.bool_value = v
        elif isinstance(v, int):
            pb_v.integer_value = v
        elif isinstance(v, float):
            pb_v.double_value = v
        else:
            pb_v.string_value = json.dumps(v)
        pb_attrs[k] = pb_v
    return pb_attrs


def _convert_span(span: tracesdk.ReadableSpan) -> pb.Span | None:
    if span.context is None:
        return None
    return pb.Span(
        span_id=trace.format_span_id(span.context.span_id),
        name=span.name,
        start_time=_proto_timestamp_from_time_ns(span.start_time),
        end_time=_proto_timestamp_from_time_ns(span.end_time),
        attributes=_convert_span_attributes(span.attributes),
    )


def convert_spans(spans: list[tracesdk.ReadableSpan]) -> list[pb.Span]:
    """
    Convert a list of spans to a list of protobuf spans.
    """
    roots: list[tracesdk.ReadableSpan] = []
    by_parent_id: dict[int, list[tracesdk.ReadableSpan]] = {}
    for span in spans:
        parent = span.parent
        if parent is None or parent.is_remote:
            roots.append(span)
            continue
        children = by_parent_id.get(parent.span_id, [])
        children.append(span)
        by_parent_id[parent.span_id] = children

    def convert_children(span: trace.SpanContext | None) -> list[pb.Span]:
        if span is None:
            return []
        pb_children: list[pb.Span] = []
        for child in by_parent_id.get(span.span_id, []):
            pb_child = _convert_span(child)
            if pb_child is None:
                continue
            pb_child.child_spans.extend(convert_children(child.context))
            pb_children.append(pb_child)
        return pb_children

    pb_spans: list[pb.Span] = []
    for span in roots:
        pb_span = _convert_span(span)
        if pb_span is None:
            continue
        pb_span.child_spans.extend(convert_children(span.context))
        pb_spans.append(pb_span)
    return pb_spans


current_spans_context_var = contextvars.ContextVar[list[tracesdk.ReadableSpan] | None](
    "redpanda_runtime_spans", default=None
)
"""
A passthrough mechanism to collect spans for a single caller.
"""


class PassthroughTraceCollector(traceexport.SpanExporter):
    """
    PassthroughSpanExporter is a no-op span exporter that collects spans
    by passing them to another context variable.

    Must be used with SimpleSpanProcessor.
    """

    @override
    def export(self, spans: Sequence[tracesdk.ReadableSpan]) -> traceexport.SpanExportResult:
        s = current_spans_context_var.get()
        if s is not None:
            s.extend(spans)
        return traceexport.SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        pass

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
