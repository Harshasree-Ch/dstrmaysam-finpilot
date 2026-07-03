from __future__ import annotations

from finpilot.core.models import AgentFinding, Evidence
from finpilot.financial_tools import FinancialTools


class NewsIntelligenceAgent:
    name = "News Intelligence Agent"

    def __init__(self, server: FinancialTools) -> None:
        self.server = server

    def run(self, ticker: str) -> AgentFinding:
        news = self.server.latest_news(ticker)
        evidence = [
            Evidence(
                source=item["source"],
                title=item["title"],
                url=item.get("url"),
                excerpt=item["summary"],
                reliability="medium",
            )
            for item in news
        ]
        return AgentFinding(
            agent_name=self.name,
            headline=f"Recent {ticker.upper()} news flow is being monitored",
            summary=(
                f"FinPilot reviewed {len(news)} recent market/news items that specifically reference "
                f"{ticker.upper()} or its company name."
            ),
            score=0.15 if news else 0.0,
            evidence=evidence,
        )
