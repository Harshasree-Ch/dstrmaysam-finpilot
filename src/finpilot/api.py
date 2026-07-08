from __future__ import annotations

import json
import os
from dataclasses import fields
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from finpilot.agents.orchestrator import ResearchOrchestrator
from finpilot.agents.trading import TradingAgent
from finpilot.chat import FinanceChatAssistant
from finpilot.core.models import TradeIntent
from finpilot.core.settings import Settings
from finpilot.observability import (
    ObservabilityMiddleware,
    configure_logging,
    log_event,
    metrics_registry,
    publish_metrics_to_langfuse,
)
from finpilot.tracing import FinPilotTracer
from finpilot.trading.paper import PaperTradingService
from finpilot_mcp.client import McpFinancialToolsClient
from finpilot_mcp.server import FinancialIntelligenceServer


configure_logging()
app = FastAPI(title="FinPilot API", version="1.0.0")
app.add_middleware(ObservabilityMiddleware)
BACKEND_VERSION = 4


class RuntimeCredentials(BaseModel):
    groww_api_key: str | None = None
    groww_secret_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper_base_url: str | None = None


class ResearchRequest(BaseModel):
    query: str
    market: Literal["India", "US"] = "India"
    horizon: Literal["3 months", "6 months", "12 months", "3 years"] = "3 months"
    risk_profile: str = "Balanced"
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


class MarketTodayRequest(BaseModel):
    market: Literal["India", "US"] = "India"
    limit: int = 10
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


class ChatRequest(BaseModel):
    question: str
    market: Literal["India", "US"] = "India"
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


class PortfolioOrdersRequest(BaseModel):
    broker: Literal["Groww", "Alpaca paper"]
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


class MarketSnapshotRequest(BaseModel):
    ticker: str
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


class TradeExecuteRequest(BaseModel):
    ticker: str
    market: Literal["India", "US"] = "India"
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, ge=0)
    user_confirmed: bool = False
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


class GrowwOrderStatusRequest(BaseModel):
    order_id: str
    credentials: RuntimeCredentials = Field(default_factory=RuntimeCredentials)


def _settings(credentials: RuntimeCredentials | None = None) -> Settings:
    base = Settings.from_env()
    credentials = credentials or RuntimeCredentials()
    payload = {
        "data_mode": "live",
        "aws_region": base.aws_region,
        "bedrock_model_id": base.bedrock_model_id,
        "use_bedrock": base.use_bedrock,
        "opensearch_endpoint": base.opensearch_endpoint,
        "groww_api_key": credentials.groww_api_key or base.groww_api_key,
        "groww_secret_key": credentials.groww_secret_key or base.groww_secret_key,
        "alpaca_api_key": credentials.alpaca_api_key or base.alpaca_api_key,
        "alpaca_secret_key": credentials.alpaca_secret_key or base.alpaca_secret_key,
        "alpaca_paper_base_url": credentials.alpaca_paper_base_url or base.alpaca_paper_base_url,
        "finnhub_api_key": base.finnhub_api_key,
        "rds_database_url": base.rds_database_url,
        "mcp_tool_url": base.mcp_tool_url,
        "rag_s3_bucket": getattr(base, "rag_s3_bucket", "dstrmaysam-finpilot"),
        "finpilot_api_url": getattr(base, "finpilot_api_url", os.getenv("FINPILOT_API_URL") or None),
        "trace_enabled": base.trace_enabled,
        "langfuse_public_key": base.langfuse_public_key,
        "langfuse_secret_key": base.langfuse_secret_key,
        "langfuse_host": base.langfuse_host,
        "langfuse_project": base.langfuse_project,
        "prompt_version": base.prompt_version,
        "llm_input_cost_per_1k_usd": base.llm_input_cost_per_1k_usd,
        "llm_output_cost_per_1k_usd": base.llm_output_cost_per_1k_usd,
    }
    settings_fields = {field.name for field in fields(Settings)}
    return Settings(**{key: value for key, value in payload.items() if key in settings_fields})


def _server(settings: Settings):
    return McpFinancialToolsClient(settings=settings, timeout=5.0) if settings.mcp_tool_url else FinancialIntelligenceServer(settings=settings)


def _trading_agent(settings: Settings) -> TradingAgent:
    return TradingAgent(PaperTradingService(settings))


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "finpilot-api", "backend_version": BACKEND_VERSION}


@app.get("/observability/metrics")
def observability_metrics() -> dict[str, Any]:
    snapshot = metrics_registry.snapshot()
    publish_metrics_to_langfuse(_settings(), snapshot)
    return {"ok": True, "message": "Observability metrics were published to Langfuse.", "data": snapshot}


@app.post("/observability/publish-quality-scores")
def publish_quality_scores() -> dict[str, Any]:
    try:
        from finpilot.evaluation.runner import run_quality_evaluation

        report = run_quality_evaluation(publish_langfuse=True)
        payload = report.output_json.read_text(encoding="utf-8")
        data = json.loads(payload)
        return {
            "ok": True,
            "message": "Quality scores were published to Langfuse.",
            "data": {
                "example_count": data["example_count"],
                "summary": data["summary"],
                "generated_at": data["generated_at"],
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/research/run")
def run_research(request: ResearchRequest) -> dict[str, Any]:
    settings = _settings(request.credentials)
    server = _server(settings)
    tracer = FinPilotTracer(settings)
    trace_input = request.model_dump(exclude={"credentials"})
    try:
        with tracer.trace(
            "finpilot.research.run",
            input_data=trace_input,
            metadata={"endpoint": "/research/run", "market": request.market},
        ) as trace:
            with tracer.span(trace, "resolve_symbol", trace_input):
                resolved_symbol = server.resolve_symbol(request.query, market=request.market)
            ticker = str(resolved_symbol["ticker"]).upper()
            if request.market == "India" and not ticker.endswith((".NS", ".BO")):
                raise ValueError("For Indian stocks, use an NSE/BSE ticker or company name.")
            if request.market == "US" and ticker.endswith((".NS", ".BO")):
                raise ValueError("For US stocks, use a US ticker or company name.")

            with tracer.span(
                trace,
                "multi_agent_research",
                {"ticker": ticker, "horizon": request.horizon, "risk_profile": request.risk_profile},
            ):
                report = ResearchOrchestrator(server).run(
                    ticker=ticker,
                    horizon=request.horizon,
                    risk_profile=request.risk_profile,
                )
            with tracer.span(trace, "fetch_display_data", {"ticker": report.ticker}):
                response = {
                    "ok": True,
                    "resolved_symbol": resolved_symbol,
                    "report": report.model_dump(),
                    "snapshot": server.market_snapshot(report.ticker),
                    "history": server.price_history(report.ticker, request.horizon),
                    "profile": server.company_profile(report.ticker),
                    "earnings": server.latest_earnings(report.ticker),
                    "news_items": server.latest_news(report.ticker),
                }
            log_event(
                "finpilot_research_completed",
                {
                    "ticker": report.ticker,
                    "recommendation": report.recommendation,
                    "confidence_score": report.confidence_score,
                    "suggested_allocation": report.suggested_allocation,
                },
                settings,
            )
            return response
    except Exception as exc:
        log_event("finpilot_research_failed", {"query": request.query, "error": str(exc)}, settings)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/market/today")
def market_today(request: MarketTodayRequest) -> dict[str, Any]:
    settings = _settings(request.credentials)
    tracer = FinPilotTracer(settings)
    try:
        with tracer.trace(
            "finpilot.market.today",
            input_data=request.model_dump(exclude={"credentials"}),
            metadata={"endpoint": "/market/today", "market": request.market},
        ) as trace:
            with tracer.span(trace, "top_stocks", {"market": request.market, "limit": request.limit}):
                return {"ok": True, "data": _server(settings).top_stocks(request.market, limit=request.limit)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/market/snapshot")
def market_snapshot(request: MarketSnapshotRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "data": _server(_settings(request.credentials)).market_snapshot(request.ticker)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/portfolio/orders")
def portfolio_orders(request: PortfolioOrdersRequest) -> dict[str, Any]:
    try:
        agent = _trading_agent(_settings(request.credentials))
        data = agent.groww_orders() if request.broker == "Groww" else agent.alpaca_orders()
        return {"ok": True, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/trade/execute")
def trade_execute(request: TradeExecuteRequest) -> dict[str, Any]:
    try:
        settings = _settings(request.credentials)
        intent = TradeIntent(
            ticker=request.ticker,
            market=request.market,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            limit_price=request.limit_price,
            user_confirmed=request.user_confirmed,
        )
        result = _trading_agent(settings).execute(intent)
        return {"ok": True, "data": result.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/trade/groww-order-status")
def groww_order_status(request: GrowwOrderStatusRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "data": _trading_agent(_settings(request.credentials)).groww_order_status(request.order_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/chat/answer")
def chat_answer(request: ChatRequest) -> dict[str, Any]:
    settings = _settings(request.credentials)
    server = _server(settings)
    trading_agent = _trading_agent(settings)
    assistant = FinanceChatAssistant(server=server, trading_agent=trading_agent, settings=settings)
    tracer = FinPilotTracer(settings)
    try:
        with tracer.trace(
            "finpilot.chat.answer",
            input_data=request.model_dump(exclude={"credentials"}),
            metadata={"endpoint": "/chat/answer", "market": request.market},
        ) as trace:
            with tracer.span(trace, "chat_assistant_answer", {"question": request.question, "market": request.market}):
                answer = assistant.answer(request.question, market=request.market)
            return {"ok": True, "answer": answer}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
