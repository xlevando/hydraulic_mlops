"""Настройка OpenTelemetry для трассировки."""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio


def setup_tracing(service_name: str | None = None) -> TracerProvider:
    """Инициализировать OTel SDK."""
    # Если service_name не передан, берем из env
    if service_name is None:
        service_name = os.getenv("OTEL_SERVICE_NAME", "hydraulic-mlops")

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://hydraulic-otel-collector:4317")
    sampler_ratio = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.2",
            "deployment.environment.name": os.getenv("ENVIRONMENT", "development"),
        }
    )

    provider = TracerProvider(
        resource=resource,
        sampler=ParentBasedTraceIdRatio(sampler_ratio),
    )

    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=100))

    trace.set_tracer_provider(provider)
    return provider
