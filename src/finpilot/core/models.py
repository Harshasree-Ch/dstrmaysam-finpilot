from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str
    title: str
    url: str | None = None
    excerpt: str
    reliability: Literal["high", "medium", "low"] = "medium"


class AgentFinding(BaseModel):
    agent_name: str
    headline: str
    summary: str
    score: float = Field(ge=-1.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)


class InvestmentReport(BaseModel):
    ticker: str
    title: str
    recommendation: Literal["Avoid", "Watch", "Hold", "Accumulate", "Buy"]
    investment_summary: str
    strengths: list[str]
    risks: list[str]
    evidence: list[Evidence]
    agent_findings: list[AgentFinding]
    suggested_allocation: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    reflection_notes: str


class TradeIntent(BaseModel):
    ticker: str
    market: Literal["India", "US"] = "India"
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, ge=0)
    user_confirmed: bool = False


class TradeResult(BaseModel):
    accepted: bool
    status: str
    message: str
    order_id: str | None = None
