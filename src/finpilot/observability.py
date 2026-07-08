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


@dataclass
class LlmMetrics:
    call_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class MetricsRegistry:
    def __init__(self) -> None:
        self._routes: dict[str, RouteMetrics] = defaultdict(RouteMetrics)
        self._agent_latencies_ms: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=500))
        self._llm = LlmMetrics()
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=100)

    def record(
        self,
        route: str,
        latency_ms: float,
        status_code: int,
        *,
        event_type: str = "request",
        agent: str | None = None,
        question: str | None = None,
        model_id: str | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        metrics = self._routes[route]
        metrics.request_count += 1
        metrics.latencies_ms.append(latency_ms)
        if status_code >= 400:
            metrics.error_count += 1
        if agent:
            self._agent_latencies_ms[agent].append(latency_ms)
        self._append_recent_event(
            {
                "event_type": event_type,
                "agent": agent,
                "route": route,
                "question": question,
                "model_id": model_id,
                "latency_ms": round(latency_ms, 2),
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "status_code": status_code,
            }
        )

    def record_llm_call(
        self,
        *,
        agent: str | None,
        model_id: str,
        latency_ms: float,
        total_tokens: int,
        cost_usd: float,
    ) -> None:
        self._llm.call_count += 1
        self._llm.total_tokens += total_tokens
        self._llm.total_cost_usd += cost_usd
        if agent:
            self._agent_latencies_ms[agent].append(latency_ms)
        self._append_recent_event(
            {
                "event_type": "llm_call",
                "agent": agent,
                "route": None,
                "question": None,
                "model_id": model_id,
                "latency_ms": round(latency_ms, 2),
                "total_tokens": total_tokens,
                "cost_usd": round(cost_usd, 8),
                "status_code": None,
            }
        )

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
            "llm_call_count": self._llm.call_count,
            "llm_total_tokens": self._llm.total_tokens,
            "llm_total_cost_usd": round(self._llm.total_cost_usd, 8),
            "average_cost_per_request_usd": round(self._llm.total_cost_usd / total_requests, 8)
            if total_requests
            else 0,
            "average_tokens_per_request": round(self._llm.total_tokens / total_requests, 2) if total_requests else 0,
            "average_latency_by_agent": {
                agent: round(mean(latencies), 2) if latencies else 0
                for agent, latencies in sorted(self._agent_latencies_ms.items())
            },
            "recent_events": list(self._recent_events),
            "routes": routes,
        }

    def _append_recent_event(self, payload: dict[str, Any]) -> None:
        self._recent_events.appendleft(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **payload,
            }
        )


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
            _trace_http_request(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "latency_ms": round(latency_ms, 2),
                    "error": error,
                }
            )


def log_event(event_name: str, payload: dict[str, Any], settings: Settings | None = None) -> None:
    if event_name == "finpilot_llm_call":
        metrics_registry.record_llm_call(
            agent=payload.get("agent"),
            model_id=str(payload.get("model") or payload.get("model_id") or "unknown"),
            latency_ms=float(payload.get("latency_ms") or 0),
            total_tokens=int(payload.get("total_tokens") or 0),
            cost_usd=float(payload.get("estimated_cost_usd") or payload.get("cost_per_query_usd") or 0),
        )
    event = {
        "event": event_name,
        "service": "finpilot-api",
        "project": (settings.langfuse_project if settings else "dstrmaysam-finpilot"),
        "timestamp_ms": int(time.time() * 1000),
        **payload,
    }
    logger.info(json.dumps(event, default=str))


def publish_metrics_to_langfuse(settings: Settings, snapshot: dict[str, Any] | None = None) -> None:
    from finpilot.tracing import FinPilotTracer

    snapshot = snapshot or metrics_registry.snapshot()
    tracer = FinPilotTracer(settings)
    with tracer.trace(
        "finpilot.observability.metrics_snapshot",
        input_data={"service": snapshot.get("service")},
        metadata={
            "request_volume": snapshot.get("request_volume", 0),
            "error_count": snapshot.get("error_count", 0),
            "error_rate": snapshot.get("error_rate", 0),
            "average_latency_ms": snapshot.get("average_latency_ms", 0),
            "p50_latency_ms": snapshot.get("p50_latency_ms", 0),
            "p95_latency_ms": snapshot.get("p95_latency_ms", 0),
            "llm_call_count": snapshot.get("llm_call_count", 0),
            "llm_total_tokens": snapshot.get("llm_total_tokens", 0),
            "llm_total_cost_usd": snapshot.get("llm_total_cost_usd", 0),
            "average_cost_per_request_usd": snapshot.get("average_cost_per_request_usd", 0),
            "average_tokens_per_request": snapshot.get("average_tokens_per_request", 0),
            "average_latency_by_agent": snapshot.get("average_latency_by_agent", {}),
            "recent_events": snapshot.get("recent_events", [])[:20],
        },
    ):
        for name, value in {
            "requests": snapshot.get("request_volume", 0),
            "error_rate": snapshot.get("error_rate", 0),
            "avg_latency_ms": snapshot.get("average_latency_ms", 0),
            "p50_latency_ms": snapshot.get("p50_latency_ms", 0),
            "p95_latency_ms": snapshot.get("p95_latency_ms", 0),
            "llm_calls": snapshot.get("llm_call_count", 0),
            "tokens": snapshot.get("llm_total_tokens", 0),
            "llm_cost_usd": snapshot.get("llm_total_cost_usd", 0),
            "avg_cost_per_request_usd": snapshot.get("average_cost_per_request_usd", 0),
            "avg_tokens_per_request": snapshot.get("average_tokens_per_request", 0),
        }.items():
            tracer.score_current_trace(name, float(value), comment="FinPilot observability metric")
    tracer.flush()


def _trace_http_request(payload: dict[str, Any]) -> None:
    try:
        from finpilot.tracing import FinPilotTracer

        settings = Settings.from_env()
        tracer = FinPilotTracer(settings)
        with tracer.trace(
            "finpilot.observability.http_request",
            input_data={"method": payload.get("method"), "path": payload.get("path")},
            metadata=payload,
        ):
            tracer.score_current_trace("request_latency_ms", float(payload.get("latency_ms") or 0))
            tracer.score_current_trace("request_error", 1.0 if int(payload.get("status_code") or 500) >= 400 else 0.0)
        tracer.flush()
    except Exception:
        return
