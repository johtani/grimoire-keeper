"""OpenTelemetry設定モジュール"""

import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def telemetry_enabled() -> bool:
    """Return whether telemetry export was explicitly configured."""
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        return False
    enabled = os.getenv("OTEL_ENABLED", "false").lower() == "true"
    return enabled or bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_telemetry(service_name: str, service_version: str = "0.1.0") -> bool:
    """OpenTelemetryを初期化し、有効な場合はTrueを返す."""

    if not telemetry_enabled():
        return False

    # OTel Collectorのエンドポイント
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # リソース情報
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "service.namespace": "grimoire-keeper",
            "service.component": service_name.removeprefix("grimoire-"),
        }
    )

    # TracerProviderの設定
    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    span_processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)

    # MeterProviderの設定
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    return True


def redact_http_url(span: trace.Span, request: object) -> None:
    """Remove request URLs from automatically generated HTTP client spans."""
    del request
    if not span.is_recording():
        return
    for attribute in ("url.full", "http.url", "http.target"):
        span.set_attribute(attribute, "[REDACTED]")


def get_tracer(name: str) -> trace.Tracer:
    """Tracerの取得"""
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Meterの取得"""
    return metrics.get_meter(name)
