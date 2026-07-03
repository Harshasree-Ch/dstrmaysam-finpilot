from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finpilot.core.models import Evidence
from finpilot.core.settings import Settings


@dataclass
class ToolCallRecorder:
    calls: list[str] = field(default_factory=list)

    def record(self, tool_name: str) -> None:
        self.calls.append(tool_name)


class EvaluationFinancialServer:
    settings = Settings()

    def __init__(self, recorder: ToolCallRecorder | None = None) -> None:
        self.recorder = recorder or ToolCallRecorder()

    def resolve_symbol(self, query: str, market: str | None = None) -> dict[str, Any]:
        self.recorder.record("resolve_symbol")
        lowered = query.lower()
        if "apple" in lowered or "aapl" in lowered:
            return {"query": query, "ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"}
        if "infosys" in lowered or "infy" in lowered:
            return {"query": query, "ticker": "INFY.NS", "name": "Infosys Limited", "exchange": "NSE"}
        if "sbi" in lowered:
            return {"query": query, "ticker": "SBIN.NS", "name": "State Bank of India", "exchange": "NSE"}
        if "tcs" in lowered:
            return {"query": query, "ticker": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE"}
        return {"query": query, "ticker": query.strip().upper(), "name": query.strip().upper(), "exchange": "NASDAQ/NYSE"}

    def company_profile(self, ticker: str) -> dict[str, Any]:
        self.recorder.record("company_profile")
        symbol = ticker.upper()
        profiles = {
            "TCS.NS": {
                "name": "Tata Consultancy Services",
                "sector": "Technology",
                "industry": "Information Technology Services",
                "market_cap": "Large Cap",
                "business_model": "IT services, consulting, and digital transformation.",
                "metrics": {"market_cap": "13.5T", "pe_ratio_ttm": "27.1", "roe": "48.2%"},
            },
            "INFY.NS": {
                "name": "Infosys Limited",
                "sector": "Technology",
                "industry": "Information Technology Services",
                "market_cap": "Large Cap",
                "business_model": "IT services, consulting, and cloud modernization.",
                "metrics": {"market_cap": "6.2T", "pe_ratio_ttm": "24.5", "roe": "31.4%"},
            },
            "AAPL": {
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "market_cap": "Mega Cap",
                "business_model": "Consumer hardware, software, and services ecosystem.",
                "metrics": {"market_cap": "2.9T", "pe_ratio_ttm": "31.8", "roe": "N/A"},
            },
            "MSFT": {
                "name": "Microsoft Corporation",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": "Mega Cap",
                "business_model": "Cloud, productivity software, and enterprise platforms.",
                "metrics": {"market_cap": "3.1T", "pe_ratio_ttm": "35.2", "roe": "33.6%"},
            },
        }
        if symbol == "XYZUNKNOWN":
            raise RuntimeError("symbol not found")
        profile = profiles.get(
            symbol,
            {
                "name": symbol,
                "sector": "Unknown",
                "industry": "Unknown",
                "market_cap": "N/A",
                "business_model": "Company profile unavailable.",
                "metrics": {},
            },
        )
        return {"ticker": symbol, "quote": self.market_snapshot(symbol), **profile}

    def company_financials(self, ticker: str) -> dict[str, Any]:
        self.recorder.record("company_financials")
        return {"revenue_growth": 0.08, "gross_margin": 0.34, "net_margin": 0.11, "debt_to_equity": 0.22}

    def competitor_analysis(self, ticker: str) -> list[str]:
        self.recorder.record("competitor_analysis")
        return ["INFY.NS", "WIPRO.NS"] if ticker.upper().endswith(".NS") else ["MSFT", "GOOGL"]

    def latest_news(self, ticker: str) -> list[dict[str, Any]]:
        self.recorder.record("latest_news")
        return [{"source": "Evaluation News", "title": f"{ticker} update", "summary": f"{ticker} has recent market updates."}]

    def latest_earnings(self, ticker: str) -> dict[str, Any]:
        self.recorder.record("latest_earnings")
        return {"quarter": "Latest quarter", "guidance": f"{ticker} earnings guidance reviewed.", "risks": ["Margin pressure"]}

    def search_documents(self, query: str) -> list[Evidence]:
        self.recorder.record("finpilot_rag_search_documents")
        self.recorder.record("search_documents")
        return [
            Evidence(
                source="FinPilot methodology PDF",
                title="Recommendation Mapping",
                excerpt=(
                    "Recommendation Mapping: scores from 55 to 74 map to Hold when evidence is mixed. "
                    "Confidence Calculation uses data_coverage_bonus, source_agreement_bonus, signal_strength_bonus, "
                    "missing_data_penalty, and conflict_penalty. Suggested Allocation Rules cap Hold allocations "
                    "around 3% to 6%. Limitations and Guardrails state FinPilot is a research aid, not financial advice, "
                    "and does not guarantee returns."
                ),
            ),
            Evidence(
                source="FinPilot methodology PDF",
                title="Research Score Formula",
                excerpt=(
                    "The total score blends price performance, fundamentals, earnings, news, and RAG document evidence. "
                    "Missing fundamentals reduce confidence because evidence coverage is incomplete."
                ),
            ),
        ]

    def market_snapshot(self, ticker: str) -> dict[str, Any]:
        self.recorder.record("market_snapshot")
        symbol = ticker.upper()
        if symbol == "XYZUNKNOWN":
            raise RuntimeError("symbol not found")
        prices = {"TCS.NS": 3500.0, "INFY.NS": 1550.0, "AAPL": 195.0, "MSFT": 430.0}
        currency = "INR" if symbol.endswith((".NS", ".BO")) else "USD"
        return {
            "ticker": symbol,
            "price": prices.get(symbol, 100.0),
            "previous_close": prices.get(symbol, 100.0) * 0.99,
            "change_percent": 0.01,
            "currency": currency,
            "exchange": "NSE" if symbol.endswith(".NS") else "NASDAQ",
        }

    def price_history(self, ticker: str, horizon: str) -> dict[str, Any]:
        self.recorder.record("price_history")
        currency = "INR" if ticker.upper().endswith((".NS", ".BO")) else "USD"
        return {
            "ticker": ticker.upper(),
            "horizon": horizon,
            "currency": currency,
            "start_date": "2026-04-01",
            "end_date": "2026-07-01",
            "start_price": 100.0,
            "end_price": 106.0,
            "change": 6.0,
            "change_percent": 0.06,
            "period_low": 96.0,
            "period_high": 109.0,
            "source": "Evaluation market fixture",
            "points": [],
        }

    def market_status(self) -> dict[str, Any]:
        self.recorder.record("market_status")
        return {"is_open": True}

    def buying_power(self) -> float:
        self.recorder.record("buying_power")
        return 25000.0

    def top_stocks(self, market: str, limit: int = 10) -> dict[str, Any]:
        self.recorder.record("top_stocks")
        symbols = ["TCS.NS", "INFY.NS"] if market == "India" else ["AAPL", "MSFT"]
        return {
            "market": market,
            "rows": [
                {
                    "ticker": symbol,
                    "company": self.company_profile(symbol)["name"],
                    "price": self.market_snapshot(symbol)["price"],
                    "change_percent": 0.01,
                    "market_cap": self.company_profile(symbol)["metrics"].get("market_cap", "N/A"),
                    "sector": self.company_profile(symbol)["sector"],
                    "status": "Live",
                }
                for symbol in symbols[:limit]
            ],
        }
