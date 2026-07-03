from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from finpilot.core.settings import Settings


logger = logging.getLogger("finpilot.observability")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


@dataclass
class RouteMetrics:
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    request_count: int = 0
    error_count: int = 0


class MetricsRegistry:
    def __init__(self) -> None:
        self._routes: dict[str, RouteMetrics] = defaultdict(RouteMetrics)

    def record(self, route: str, latency_ms: float, status_code: int) -> None:
        metrics = self._routes[route]
        metrics.request_count += 1
        metrics.latencies_ms.append(latency_ms)
        if status_code >= 400:
            metrics.error_count += 1

    def snapshot(self) -> dict[str, Any]:
        routes = {}
        total_requests = 0
        total_errors = 0
        all_latencies = []
        for route, metrics in sorted(self._routes.items()):
            latencies = sorted(metrics.latencies_ms)
            total_requests += metrics.request_count
            total_errors += metrics.error_count
            all_latencies.extend(latencies)
            routes[route] = {
                "request_volume": metrics.request_count,
                "error_count": metrics.error_count,
                "error_rate": _safe_rate(metrics.error_count, metrics.request_count),
                "average_latency_ms": round(mean(latencies), 2) if latencies else 0,
                "p50_latency_ms": round(_percentile(latencies, 50), 2),
                "p95_latency_ms": round(_percentile(latencies, 95), 2),
            }
        all_latencies.sort()
        return {
            "service": "finpilot-api",
            "request_volume": total_requests,
            "error_count": total_errors,
            "error_rate": _safe_rate(total_errors, total_requests),
            "average_latency_ms": round(mean(all_latencies), 2) if all_latencies else 0,
            "p50_latency_ms": round(_percentile(all_latencies, 50), 2),
            "p95_latency_ms": round(_percentile(all_latencies, 95), 2),
            "routes": routes,
        }


def _safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, round((percentile / 100) * (len(values) - 1)))
    return values[index]


metrics_registry = MetricsRegistry()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status_code = 500
        error = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            route = f"{request.method} {request.url.path}"
            metrics_registry.record(route, latency_ms, status_code)
            log_event(
                "finpilot_http_request",
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "latency_ms": round(latency_ms, 2),
                    "error": error,
                },
            )


def log_event(event_name: str, payload: dict[str, Any], settings: Settings | None = None) -> None:
    event = {
        "event": event_name,
        "service": "finpilot-api",
        "project": (settings.langfuse_project if settings else "dstrmaysam-finpilot"),
        "timestamp_ms": int(time.time() * 1000),
        **payload,
    }
    logger.info(json.dumps(event, default=str))
