from __future__ import annotations

from finpilot.core.models import AgentFinding, Evidence
from finpilot.financial_tools import FinancialTools


class CompanyIntelligenceAgent:
    name = "Company Intelligence Agent"

    def __init__(self, server: FinancialTools) -> None:
        self.server = server

    def run(self, ticker: str) -> AgentFinding:
        profile = self.server.company_profile(ticker)
        financials = self.server.company_financials(ticker)
        gross_margin = financials["gross_margin"]
        net_margin = financials["net_margin"]
        gross_margin_text = f"{gross_margin:.0%}" if gross_margin else "unavailable"
        net_margin_text = f"{net_margin:.0%}" if net_margin else "unavailable"
        price_text = ""
        if profile.get("quote", {}).get("price") is not None:
            quote = profile["quote"]
            price_text = f" Latest price is {quote['currency']} {quote['price']:,.2f}."
        evidence = [
            Evidence(
                source="Yahoo Finance",
                title=f"{profile['name']} business overview",
                excerpt=f"{profile['business_model']}{price_text}",
                reliability="medium",
            )
        ]
        score = min(0.8, financials["revenue_growth"] + gross_margin)
        return AgentFinding(
            agent_name=self.name,
            headline=f"{profile['name']} realtime company profile reviewed",
            summary=(
                f"{profile['name']} operates in {profile['industry']} with a {profile['market_cap']} profile. "
                f"Gross margin is {gross_margin_text}, while net margin is {net_margin_text}.{price_text}"
            ),
            score=score,
            evidence=evidence,
        )
