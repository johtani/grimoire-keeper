from unittest.mock import MagicMock, call

import pytest
from grimoire_shared import telemetry


def test_setup_telemetry_returns_early_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_create = MagicMock()
    monkeypatch.setenv("OTEL_SDK_DISABLED", "TRUE")
    monkeypatch.setattr(telemetry.Resource, "create", resource_create)

    assert telemetry.setup_telemetry("test-service") is False

    resource_create.assert_not_called()


def test_setup_telemetry_returns_early_without_explicit_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_create = MagicMock()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry.Resource, "create", resource_create)

    assert telemetry.setup_telemetry("test-service") is False

    resource_create.assert_not_called()


def test_setup_telemetry_configures_tracing_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = MagicMock()
    tracer_provider = MagicMock()
    span_exporter = MagicMock()
    span_processor = MagicMock()
    metric_exporter = MagicMock()
    metric_reader = MagicMock()
    meter_provider = MagicMock()
    resource_create = MagicMock(return_value=resource)
    tracer_provider_factory = MagicMock(return_value=tracer_provider)
    span_exporter_factory = MagicMock(return_value=span_exporter)
    span_processor_factory = MagicMock(return_value=span_processor)
    metric_exporter_factory = MagicMock(return_value=metric_exporter)
    metric_reader_factory = MagicMock(return_value=metric_reader)
    meter_provider_factory = MagicMock(return_value=meter_provider)

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    monkeypatch.setattr(telemetry.Resource, "create", resource_create)
    monkeypatch.setattr(telemetry, "TracerProvider", tracer_provider_factory)
    monkeypatch.setattr(telemetry, "OTLPSpanExporter", span_exporter_factory)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", span_processor_factory)
    monkeypatch.setattr(telemetry, "OTLPMetricExporter", metric_exporter_factory)
    monkeypatch.setattr(
        telemetry,
        "PeriodicExportingMetricReader",
        metric_reader_factory,
    )
    monkeypatch.setattr(telemetry, "MeterProvider", meter_provider_factory)
    set_tracer_provider = MagicMock()
    set_meter_provider = MagicMock()
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", set_tracer_provider)
    monkeypatch.setattr(telemetry.metrics, "set_meter_provider", set_meter_provider)

    assert telemetry.setup_telemetry("test-service", "2.0.0") is True

    resource_create.assert_called_once_with(
        {
            "service.name": "test-service",
            "service.version": "2.0.0",
            "service.namespace": "grimoire-keeper",
            "service.component": "test-service",
        }
    )
    span_exporter_factory.assert_called_once_with(
        endpoint="http://collector:4317", insecure=True
    )
    metric_exporter_factory.assert_called_once_with(
        endpoint="http://collector:4317", insecure=True
    )
    tracer_provider.add_span_processor.assert_called_once_with(span_processor)
    set_tracer_provider.assert_called_once_with(tracer_provider)
    metric_reader_factory.assert_called_once_with(
        metric_exporter, export_interval_millis=5000
    )
    meter_provider_factory.assert_called_once_with(
        resource=resource, metric_readers=[metric_reader]
    )
    set_meter_provider.assert_called_once_with(meter_provider)


def test_redact_http_url_replaces_sensitive_attributes() -> None:
    span = MagicMock()
    span.is_recording.return_value = True

    telemetry.redact_http_url(span, object())

    assert span.set_attribute.call_args_list == [
        call("url.full", "[REDACTED]"),
        call("http.url", "[REDACTED]"),
        call("http.target", "[REDACTED]"),
    ]


def test_get_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = MagicMock()
    get_tracer = MagicMock(return_value=tracer)
    monkeypatch.setattr(telemetry.trace, "get_tracer", get_tracer)

    assert telemetry.get_tracer("test") is tracer
    get_tracer.assert_called_once_with("test")


def test_get_meter(monkeypatch: pytest.MonkeyPatch) -> None:
    meter = MagicMock()
    get_meter = MagicMock(return_value=meter)
    monkeypatch.setattr(telemetry.metrics, "get_meter", get_meter)

    assert telemetry.get_meter("test") is meter
    get_meter.assert_called_once_with("test")
