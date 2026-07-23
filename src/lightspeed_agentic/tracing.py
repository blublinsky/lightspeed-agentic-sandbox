"""OTEL tracing — tracer initialization and traceparent parsing.

Relies on the OTEL Python SDK's built-in environment variable handling.
Standard OTEL_* env vars (OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES,
OTEL_EXPORTER_OTLP_HEADERS, OTEL_EXPORTER_OTLP_INSECURE, etc.) are read
by the SDK automatically — no manual parsing needed.

This module adds:
- OTEL_EXPORTER_OTLP_PROTOCOL: selects gRPC vs http/protobuf exporter
- OTEL_TRACES_EXPORTER=none: disables span export even when endpoint is set
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

_DEFAULT_SERVICE_NAME = "lightspeed-agentic-sandbox"
_TRACER_NAME = "lightspeed_agentic"
_tracer_provider: TracerProvider | None = None
_logger = logging.getLogger(__name__)


class OTLPJsonStdoutExporter(SpanExporter):
    """Exports spans as OTLP JSON wire format to stdout (one line per batch)."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        import json as _json

        from google.protobuf.json_format import MessageToDict  # type: ignore[import-untyped]
        from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans

        pb = encode_spans(spans)
        line = _json.dumps(MessageToDict(pb, preserving_proto_field_name=True))
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def init_tracer(*, audit_enabled: bool = False) -> None:
    """Initialize the OTEL tracer provider.

    If OTEL_EXPORTER_OTLP_ENDPOINT is not set or OTEL_TRACES_EXPORTER is
    ``none``, creates a no-op tracer (no spans exported).
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return

    resource = Resource.create()
    if resource.attributes.get(SERVICE_NAME) == "unknown_service":
        resource = resource.merge(Resource({SERVICE_NAME: _DEFAULT_SERVICE_NAME}))
    _tracer_provider = TracerProvider(resource=resource)
    if audit_enabled:
        _tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPJsonStdoutExporter()))

    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    ).strip()
    traces_exporter = os.environ.get("OTEL_TRACES_EXPORTER", "otlp").strip().lower()

    if traces_exporter not in ("otlp", "none"):
        _logger.warning("unsupported OTEL_TRACES_EXPORTER=%r, disabling export", traces_exporter)
        traces_exporter = "none"

    if endpoint and traces_exporter != "none":
        protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").strip().lower()
        if protocol not in ("grpc", "http/protobuf", ""):
            _logger.warning(
                "unsupported OTEL_EXPORTER_OTLP_PROTOCOL=%r, defaulting to grpc", protocol
            )
            protocol = "grpc"

        exporter: SpanExporter
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter as HttpExporter,
            )

            exporter = HttpExporter(endpoint=endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter as GrpcExporter,
            )

            exporter = GrpcExporter(endpoint=endpoint)

        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(_tracer_provider)


def shutdown_tracer() -> None:
    """Shutdown the tracer provider, flushing any pending spans."""
    if _tracer_provider:
        _tracer_provider.shutdown()


def get_tracer() -> trace.Tracer:
    """Get a tracer instance for creating spans."""
    return trace.get_tracer(_TRACER_NAME)


def parse_traceparent(header: str | None) -> tuple[str, Context | None]:
    """Parse W3C traceparent header and return (trace_id, context).

    If the header is invalid or missing, generates a new trace ID.
    """
    if header:
        parts = header.split("-")
        if len(parts) >= 4:
            trace_id_hex = parts[1]
            parent_id_hex = parts[2]
            flags_hex = parts[3]
            if (
                len(trace_id_hex) == 32
                and trace_id_hex != "0" * 32
                and len(parent_id_hex) == 16
                and parent_id_hex != "0" * 16
            ):
                try:
                    trace_id = int(trace_id_hex, 16)
                    parent_id = int(parent_id_hex, 16)
                    flags = int(flags_hex, 16)
                except ValueError:
                    return _generate_trace_id()
                span_ctx = SpanContext(
                    trace_id=trace_id,
                    span_id=parent_id,
                    is_remote=True,
                    trace_flags=TraceFlags(flags),
                )
                ctx = trace.set_span_in_context(NonRecordingSpan(span_ctx))
                return trace_id_hex, ctx
    return _generate_trace_id()


def _generate_trace_id() -> tuple[str, Context]:
    """Generate a new trace ID and root context."""
    trace_id_hex = secrets.token_hex(16)
    span_id_hex = secrets.token_hex(8)
    span_ctx = SpanContext(
        trace_id=int(trace_id_hex, 16),
        span_id=int(span_id_hex, 16),
        is_remote=False,
        trace_flags=TraceFlags(1),
    )
    ctx = trace.set_span_in_context(NonRecordingSpan(span_ctx))
    return trace_id_hex, ctx
