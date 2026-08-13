"""Observability: Prometheus metrics + OpenTelemetry tracing setup.

Metrics support multi-process mode (PROMETHEUS_MULTIPROC_DIR) so the API and
worker processes aggregate into one `/metrics` endpoint through a shared
volume. When the env var is unset (plain local runs) a single-process registry
is used.
"""

import os
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

METRICS_NAMESPACE = "clipforge"

_http_requests = Counter(
    f"{METRICS_NAMESPACE}_http_requests_total",
    "HTTP requests processed",
    ("method", "path", "status"),
)
_http_request_duration = Histogram(
    f"{METRICS_NAMESPACE}_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
_job_duration = Histogram(
    f"{METRICS_NAMESPACE}_job_duration_seconds",
    "Pipeline job duration in seconds",
    ("type", "status"),
)
_ai_calls = Counter(
    f"{METRICS_NAMESPACE}_ai_calls_total",
    "AI provider calls",
    ("provider", "model", "operation"),
)
_ai_duration = Histogram(
    f"{METRICS_NAMESPACE}_ai_duration_seconds",
    "AI provider call duration in seconds",
    ("provider", "model", "operation"),
)
_ai_cost = Counter(
    f"{METRICS_NAMESPACE}_ai_cost_cents_total",
    "Cumulative AI cost in cents",
    ("provider", "model"),
)
_queue_depth = Gauge(
    f"{METRICS_NAMESPACE}_queue_depth",
    "Messages pending in a queue",
    ("queue", "backend"),
    multiprocess_mode="sum",
)

_worker_duration = Histogram(
    f"{METRICS_NAMESPACE}_worker_duration_seconds",
    "Intelligence worker total execution duration",
    ("kind", "status"),
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900),
)
_worker_processing_duration = Histogram(
    f"{METRICS_NAMESPACE}_worker_processing_duration_seconds",
    "Intelligence worker detector (compute) duration",
    ("kind",),
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900),
)
_worker_queue_time = Histogram(
    f"{METRICS_NAMESPACE}_worker_queue_time_seconds",
    "Intelligence worker time spent queued before execution",
    ("kind",),
    buckets=(0, 0.1, 1, 5, 10, 30, 60, 300, 900),
)
_worker_failures = Counter(
    f"{METRICS_NAMESPACE}_worker_failures_total",
    "Intelligence worker failures",
    ("kind",),
)


_registry: CollectorRegistry | None = None


def setup_metrics() -> CollectorRegistry:
    """Build the metrics registry for this process.

    Metrics objects are module-level so every process records into the same
    names; the registry (with MultiProcessCollector when configured) is what
    varies per process. Must be called before first metric use in scrape mode.
    """
    global _registry
    if _registry is not None:
        return _registry
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    registry = CollectorRegistry()
    if multiproc_dir:
        multiprocess.MultiProcessCollector(registry)
    _registry = registry
    return registry


def render_metrics(registry: CollectorRegistry | None = None) -> tuple[bytes, str]:
    if registry is None:
        registry = setup_metrics()
    return generate_latest(registry), "text/plain; version=0.0.4; charset=utf-8"


def record_http_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    _http_requests.labels(method=method, path=path, status=str(status)).inc()
    _http_request_duration.labels(method=method, path=path).observe(duration_seconds)


def record_job_completion(job_type: str, status: str, duration_seconds: float) -> None:
    _job_duration.labels(type=job_type, status=status).observe(duration_seconds)


def record_ai_call(
    provider: str,
    model: str,
    operation: str,
    duration_seconds: float,
    cost_cents: int = 0,
) -> None:
    _ai_calls.labels(provider=provider, model=model, operation=operation).inc()
    _ai_duration.labels(provider=provider, model=model, operation=operation).observe(
        duration_seconds
    )
    if cost_cents > 0:
        _ai_cost.labels(provider=provider, model=model).inc(cost_cents)


def set_queue_depth(queue: str, depth: int) -> None:
    _queue_depth.labels(queue=queue, backend="redis").set(depth)


def record_worker_completion(
    kind: str,
    status: str,
    total_seconds: float,
    processing_seconds: float | None = None,
    queue_seconds: float | None = None,
) -> None:
    """Record an intelligence worker run.

    - `total_seconds`: actor wall time (latency).
    - `processing_seconds`: time spent inside the detector.
    - `queue_seconds`: time between the node being enqueued and execution.
    """
    _worker_duration.labels(kind=kind, status=status).observe(total_seconds)
    if processing_seconds is not None:
        _worker_processing_duration.labels(kind=kind).observe(processing_seconds)
    if queue_seconds is not None:
        _worker_queue_time.labels(kind=kind).observe(queue_seconds)
    if status == "failed":
        _worker_failures.labels(kind=kind).inc()


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def setup_tracing(service_name: str, enabled: bool) -> Any:
    """Configure OpenTelemetry and return a tracer.

    When disabled (or no exporter configured) tracing degrades to a no-op, so
    instrumented code is always safe to run.
    """
    if not enabled:
        return _noop_tracer()

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = _build_span_exporter()
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        return trace.get_tracer(service_name)
    except Exception:
        # Never let telemetry break the platform.
        return _noop_tracer()


def _build_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=endpoint)
    return ConsoleSpanExporter()


def trace_id_from_context() -> str | None:
    """Return the current trace id as hex (32 chars) or None."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        context = span.get_span_context()
        if context is not None and context.is_valid:
            return format(context.trace_id, "032x")
    except Exception:
        pass
    return None


def _noop_tracer() -> Any:
    try:
        from opentelemetry import trace

        return trace.get_tracer("clipforge-noop")
    except Exception:
        return None
