from fastapi.testclient import TestClient

from finpilot.api import app
from finpilot.observability import MetricsRegistry, log_event


def test_metrics_registry_tracks_request_and_llm_totals():
    registry = MetricsRegistry()

    registry.record("POST /research/run", 120.5, 200, agent="Stock Agent", question="Cisco share price")
    registry.record("POST /chat/answer", 10.0, 500, agent="Chat Agent", question="why hold?")
    registry.record_llm_call(
        agent="Investment Agent",
        model_id="amazon.nova-lite",
        latency_ms=42.0,
        total_tokens=12,
        cost_usd=0.000003,
    )

    snapshot = registry.snapshot()

    assert snapshot["request_volume"] == 2
    assert snapshot["error_count"] == 1
    assert snapshot["error_rate"] == 0.5
    assert snapshot["llm_call_count"] == 1
    assert snapshot["llm_total_tokens"] == 12
    assert snapshot["llm_total_cost_usd"] == 0.000003
    assert snapshot["average_cost_per_request_usd"] == 0.0000015
    assert snapshot["average_tokens_per_request"] == 6
    assert snapshot["average_latency_by_agent"]["Stock Agent"] == 120.5
    assert snapshot["recent_events"][0]["event_type"] == "llm_call"


def test_log_event_records_llm_call_metrics(monkeypatch):
    from finpilot import observability

    registry = MetricsRegistry()
    monkeypatch.setattr(observability, "metrics_registry", registry)

    log_event(
        "finpilot_llm_call",
        {
            "agent": "Investment Agent",
            "model": "amazon.titan",
            "latency_ms": 20,
            "total_tokens": 4,
            "estimated_cost_usd": 0.000001,
        },
    )

    snapshot = registry.snapshot()
    assert snapshot["llm_call_count"] == 1
    assert snapshot["llm_total_tokens"] == 4
    assert snapshot["llm_total_cost_usd"] == 0.000001


def test_observability_endpoint_publishes_and_returns_metric_payload(monkeypatch):
    published = {}

    def fake_publish(settings, snapshot):
        published["snapshot"] = snapshot

    monkeypatch.setattr("finpilot.api.publish_metrics_to_langfuse", fake_publish)

    response = TestClient(app).get("/observability/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "data" in body
    assert body["data"]["request_volume"] >= 0
    assert "published to Langfuse" in body["message"]
    assert "snapshot" in published
