from __future__ import annotations

from finpilot.core.models import AgentFinding, Evidence
from finpilot.financial_tools import FinancialTools


class MarketPerformanceAgent:
    name = "Market Performance Agent"

    def __init__(self, server: FinancialTools) -> None:
        self.server = server

    def run(self, ticker: str, horizon: str) -> AgentFinding:
        history = self.server.price_history(ticker, horizon)
        change_percent = history["change_percent"] or 0.0
        score = self._score(change_percent)
        direction = "positive" if change_percent > 0 else "negative" if change_percent < 0 else "flat"
        return AgentFinding(
            agent_name=self.name,
            headline=f"{ticker.upper()} {horizon} price trend is {direction}",
            summary=(
                f"{ticker.upper()} moved {history['change']:,.2f} ({change_percent:.2%}) from "
                f"{history['start_date']} to {history['end_date']}. The period range was "
                f"{history['currency']} {history['period_low']:,.2f} to {history['currency']} "
                f"{history['period_high']:,.2f}."
            ),
            score=score,
            evidence=[
                Evidence(
                    source=history["source"],
                    title=f"{ticker.upper()} {horizon} price performance",
                    excerpt=(
                        f"Start: {history['currency']} {history['start_price']:,.2f}; "
                        f"End: {history['currency']} {history['end_price']:,.2f}; "
                        f"Change: {change_percent:.2%}."
                    ),
                    reliability="high",
                )
            ],
        )

    def _score(self, change_percent: float) -> float:
        if change_percent >= 0.30:
            return 0.75
        if change_percent >= 0.15:
            return 0.55
        if change_percent >= 0.05:
            return 0.35
        if change_percent >= 0.0:
            return 0.15
        if change_percent >= -0.10:
            return -0.05
        if change_percent >= -0.25:
            return -0.30
        return -0.55
