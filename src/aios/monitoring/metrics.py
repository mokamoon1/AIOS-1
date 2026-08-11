"""Prometheus metrics exposition (Phase 9.6)."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response


# Request metrics
http_requests_total = Counter(
    "aios_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "aios_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Ingestion metrics
ingestion_requests_total = Counter(
    "aios_ingestion_requests_total",
    "Total ingestion requests",
    ["provider", "status"],
)

ingestion_latency_seconds = Histogram(
    "aios_ingestion_latency_seconds",
    "Ingestion latency in seconds",
    ["provider"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Decision engine metrics
decision_engine_requests_total = Counter(
    "aios_decision_engine_requests_total",
    "Total decision engine requests",
    ["decision", "status"],
)

decision_engine_latency_seconds = Histogram(
    "aios_decision_engine_latency_seconds",
    "Decision engine latency in seconds",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Broker metrics
broker_orders_total = Counter(
    "aios_broker_orders_total",
    "Total broker orders",
    ["side", "status"],
)

broker_fills_total = Counter(
    "aios_broker_fills_total",
    "Total broker fills",
    ["side"],
)

broker_fill_latency_seconds = Histogram(
    "aios_broker_fill_latency_seconds",
    "Broker fill latency in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Risk metrics
risk_evaluations_total = Counter(
    "aios_risk_evaluations_total",
    "Total risk evaluations",
    ["approval_status", "risk_level"],
)

# Shariah compliance metrics
shariah_checks_total = Counter(
    "aios_shariah_checks_total",
    "Total Shariah compliance checks",
    ["status"],
)

# Error metrics
errors_total = Counter(
    "aios_errors_total",
    "Total errors",
    ["component", "error_type"],
)

# System metrics
system_uptime_seconds = Gauge(
    "aios_system_uptime_seconds",
    "System uptime in seconds",
)

# Active components
active_agents = Gauge(
    "aios_active_agents",
    "Number of active agents",
)

active_engines = Gauge(
    "aios_active_engines",
    "Number of active engines",
)

connected_providers = Gauge(
    "aios_connected_providers",
    "Number of connected providers",
)

broker_connected = Gauge(
    "aios_broker_connected",
    "Broker connection status (1=connected, 0=disconnected)",
)


def record_http_request(method: str, endpoint: str, status: int) -> None:
    """Record an HTTP request metric."""
    http_requests_total.labels(method=method, endpoint=endpoint, status=str(status)).inc()


def record_http_latency(method: str, endpoint: str, duration: float) -> None:
    """Record HTTP request latency."""
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


def record_ingestion(provider: str, status: str, duration: float) -> None:
    """Record an ingestion request."""
    ingestion_requests_total.labels(provider=provider, status=status).inc()
    ingestion_latency_seconds.labels(provider=provider).observe(duration)


def record_decision(decision: str, status: str, duration: float) -> None:
    """Record a decision engine request."""
    decision_engine_requests_total.labels(decision=decision, status=status).inc()
    decision_engine_latency_seconds.observe(duration)


def record_broker_order(side: str, status: str) -> None:
    """Record a broker order."""
    broker_orders_total.labels(side=side, status=status).inc()


def record_broker_fill(side: str, duration: float) -> None:
    """Record a broker fill."""
    broker_fills_total.labels(side=side).inc()
    broker_fill_latency_seconds.observe(duration)


def record_risk_evaluation(approval_status: str, risk_level: str) -> None:
    """Record a risk evaluation."""
    risk_evaluations_total.labels(approval_status=approval_status, risk_level=risk_level).inc()


def record_shariah_check(status: str) -> None:
    """Record a Shariah compliance check."""
    shariah_checks_total.labels(status=status).inc()


def record_error(component: str, error_type: str) -> None:
    """Record an error."""
    errors_total.labels(component=component, error_type=error_type).inc()


def update_system_metrics(
    uptime_seconds: float,
    active_agents_count: int,
    active_engines_count: int,
    connected_providers_count: int,
    broker_is_connected: bool,
) -> None:
    """Update system-level metrics."""
    system_uptime_seconds.set(uptime_seconds)
    active_agents.set(active_agents_count)
    active_engines.set(active_engines_count)
    connected_providers.set(connected_providers_count)
    broker_connected.set(1 if broker_is_connected else 0)


def _histogram_buckets(histogram: Any) -> tuple[list[float], list[float]]:
    """Return ``(upper_bounds, cumulative_counts)`` from a Prometheus histogram.

    The histogram records per-bucket counts internally (non-cumulative); the
    cumulative series is reconstructed for percentile estimation. This reads
    the child metric for a histogram that observes with no labels, or a
    plain histogram when labels are unset.
    """
    child = histogram
    if histogram._labelnames:
        # A labeled histogram keeps its data on a default child keyed by the
        # registered label values; fall back to any single child otherwise.
        children = list(histogram._metrics.values()) if hasattr(histogram, "_metrics") else []
        if children:
            child = children[0]
    upper_bounds = [float(bound) for bound in child._upper_bounds]
    raw = [bucket.get() for bucket in child._buckets]
    cumulative: list[float] = []
    running = 0.0
    for count in raw:
        running += float(count)
        cumulative.append(running)
    return upper_bounds, cumulative


def _histogram_p99(histogram: Any) -> float | None:
    """Estimate the P99 latency in seconds from a Prometheus histogram.

    Uses linear interpolation inside the bucket containing the 99th
    percentile observation. When the target falls in the final (+Inf) bucket,
    the observed mean (sum/count) is reported instead, which is a real
    measured value and never a fabricated threshold. Returns ``None`` when no
    observation has been recorded yet.
    """
    child = histogram
    if histogram._labelnames:
        children = list(histogram._metrics.values()) if hasattr(histogram, "_metrics") else []
        if not children:
            return None
        child = children[0]
    total = float(sum(bucket.get() for bucket in child._buckets))
    if total <= 0:
        return None
    upper_bounds, cumulative = _histogram_buckets(child)
    target = 0.99 * total
    for index, upper_bound in enumerate(upper_bounds):
        if cumulative[index] < target:
            continue
        if upper_bound == float("inf"):
            return child._sum.get() / total if child._sum.get() else None
        lower_bound = upper_bounds[index - 1] if index > 0 else 0.0
        below = cumulative[index - 1] if index > 0 else 0.0
        width = upper_bound - lower_bound
        if width <= 0:
            return upper_bound
        fraction = (target - below) / (cumulative[index] - below) if cumulative[index] > below else 0.0
        return lower_bound + fraction * width
    return None


def ingestion_latency_p99_ms() -> float | None:
    """Return the measured P99 ingestion latency in milliseconds, if any."""
    seconds = _histogram_p99(ingestion_latency_seconds)
    return None if seconds is None else seconds * 1000.0


def decision_latency_p99_ms() -> float | None:
    """Return the measured P99 decision latency in milliseconds, if any."""
    seconds = _histogram_p99(decision_engine_latency_seconds)
    return None if seconds is None else seconds * 1000.0


def broker_fill_latency_p99_ms() -> float | None:
    """Return the measured P99 broker fill latency in milliseconds, if any."""
    seconds = _histogram_p99(broker_fill_latency_seconds)
    return None if seconds is None else seconds * 1000.0


def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def metrics_middleware(app: Callable) -> Callable:
    """ASGI middleware to record HTTP metrics."""
    
    @wraps(app)
    async def middleware(scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return await app(scope, receive, send)
        
        start_time = time.perf_counter()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        
        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status = message.get("status", 0)
                duration = time.perf_counter() - start_time
                record_http_request(method, path, status)
                record_http_latency(method, path, duration)
            await send(message)
        
        await app(scope, receive, send_wrapper)
    
    return middleware