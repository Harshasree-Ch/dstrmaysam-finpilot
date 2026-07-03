from __future__ import annotations

from finpilot.core.models import AgentFinding
from finpilot.financial_tools import FinancialTools


class EarningsIntelligenceAgent:
    name = "Earnings Intelligence Agent"

    def __init__(self, server: FinancialTools) -> None:
        self.server = server

    def run(self, ticker: str) -> AgentFinding:
        earnings = self.server.latest_earnings(ticker)
        evidence = self.server.search_documents(f"{ticker} earnings management guidance")
        risk_text = ", ".join(earnings["risks"])
        return AgentFinding(
            agent_name=self.name,
            headline=f"{earnings['quarter']} guidance is constructive but risk-aware",
            summary=f"{earnings['guidance']} Key risks include {risk_text}.",
            score=0.28,
            evidence=evidence,
        )
