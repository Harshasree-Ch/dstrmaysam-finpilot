from finpilot.agents.orchestrator import ResearchOrchestrator
from finpilot.agents.research import InvestmentResearchAgent
from finpilot.core.models import AgentFinding, Evidence
from finpilot.core.settings import Settings


class FakeFinancialServer:
    settings = Settings()

    def price_history(self, ticker: str, horizon: str) -> dict:
        return {
            "ticker": ticker,
            "horizon": horizon,
            "currency": "INR",
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
            "start_price": 1000.0,
            "end_price": 1080.0,
            "change": 80.0,
            "change_percent": 0.08,
            "period_low": 980.0,
            "period_high": 1100.0,
            "source": "Test fixture",
            "points": [],
        }

    def company_profile(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "name": "Reliance Industries Limited",
            "industry": "Oil & Gas Refining and Marketing",
            "market_cap": "Large Cap",
            "business_model": "Integrated energy, retail, telecom, and digital services conglomerate.",
            "quote": {"price": 1080.0, "currency": "INR"},
        }

    def company_financials(self, ticker: str) -> dict:
        return {"revenue_growth": 0.08, "gross_margin": 0.34, "net_margin": 0.09, "debt_to_equity": 0.38}

    def latest_earnings(self, ticker: str) -> dict:
        return {
            "quarter": "Latest reported quarter",
            "guidance": "Management highlighted retail scale and telecom monetization.",
            "risks": ["Execution risk"],
        }

    def latest_news(self, ticker: str) -> list[dict]:
        return [
            {
                "source": "Test News",
                "title": "Reliance market update",
                "summary": "Reliance shares were monitored in the latest market update.",
            }
        ]

    def search_documents(self, query: str) -> list[Evidence]:
        return [Evidence(source="Test Corpus", title="Earnings note", excerpt="Management guidance reviewed.")]


def test_research_workflow_generates_evidence():
    server = FakeFinancialServer()
    report = ResearchOrchestrator(server).run("RELIANCE.NS", "12 months", "Balanced")
    assert report.ticker == "RELIANCE.NS"
    assert report.evidence
    assert report.confidence_score > 0


def test_bedrock_synthesis_falls_back_when_unavailable(monkeypatch):
    agent = InvestmentResearchAgent(Settings(use_bedrock=True))
    monkeypatch.setattr(agent, "_invoke_bedrock", lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))
    findings = [
        AgentFinding(
            agent_name="Market Performance Agent",
            headline="Positive price trend",
            summary="Price performance is positive.",
            score=0.4,
            evidence=[Evidence(source="Yahoo Finance", title="Price trend", excerpt="Price rose.")],
        )
    ]

    report = agent.synthesize("RELIANCE.NS", "12 months", "Balanced", findings, "Reflection passed.")

    assert report.recommendation in {"Hold", "Accumulate", "Buy"}
    assert "Bedrock synthesis was unavailable" in report.reflection_notes


def test_bedrock_synthesis_updates_narrative(monkeypatch):
    agent = InvestmentResearchAgent(Settings(use_bedrock=True))
    monkeypatch.setattr(
        agent,
        "_invoke_bedrock",
        lambda *args: {
            "investment_summary": "Bedrock-generated summary.",
            "strengths": ["Bedrock strength"],
            "risks": ["Bedrock risk"],
            "reflection_notes": "Bedrock reflection.",
        },
    )
    findings = [
        AgentFinding(
            agent_name="Market Performance Agent",
            headline="Positive price trend",
            summary="Price performance is positive.",
            score=0.4,
            evidence=[Evidence(source="Yahoo Finance", title="Price trend", excerpt="Price rose.")],
        )
    ]

    report = agent.synthesize("RELIANCE.NS", "12 months", "Balanced", findings, "Reflection passed.")

    assert report.investment_summary == "Bedrock-generated summary."
    assert report.strengths == ["Bedrock strength"]
    assert report.risks == ["Bedrock risk"]
