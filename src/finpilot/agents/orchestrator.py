from __future__ import annotations

from typing import Any, TypedDict

from finpilot.agents.company import CompanyIntelligenceAgent
from finpilot.agents.earnings import EarningsIntelligenceAgent
from finpilot.agents.market import MarketPerformanceAgent
from finpilot.agents.news import NewsIntelligenceAgent
from finpilot.agents.reflection import ReflectionAgent
from finpilot.agents.research import InvestmentResearchAgent
from finpilot.core.models import AgentFinding, InvestmentReport
from finpilot.financial_tools import FinancialTools


class ResearchGraphState(TypedDict, total=False):
    ticker: str
    horizon: str
    risk_profile: str
    findings: list[AgentFinding]
    reflection_notes: str
    report: InvestmentReport


class ResearchOrchestrator:
    """LangGraph-backed orchestration layer for the multi-agent research workflow."""

    def __init__(self, server: FinancialTools) -> None:
        self.company = CompanyIntelligenceAgent(server)
        self.market = MarketPerformanceAgent(server)
        self.earnings = EarningsIntelligenceAgent(server)
        self.news = NewsIntelligenceAgent(server)
        self.reflection = ReflectionAgent()
        self.research = InvestmentResearchAgent(server.settings)
        self.graph = self._build_graph()
        self.uses_langgraph = self.graph is not None

    def run(self, ticker: str, horizon: str, risk_profile: str) -> InvestmentReport:
        initial_state: ResearchGraphState = {
            "ticker": ticker,
            "horizon": horizon,
            "risk_profile": risk_profile,
            "findings": [],
        }
        if self.graph is not None:
            final_state = self.graph.invoke(initial_state)
            return final_state["report"]
        return self._run_sequential(initial_state)

    def _build_graph(self) -> Any | None:
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None

        graph = StateGraph(ResearchGraphState)
        graph.add_node("market", self._run_market)
        graph.add_node("company", self._run_company)
        graph.add_node("earnings", self._run_earnings)
        graph.add_node("news", self._run_news)
        graph.add_node("reflection", self._run_reflection)
        graph.add_node("research", self._run_research)

        graph.add_edge(START, "market")
        graph.add_edge("market", "company")
        graph.add_edge("company", "earnings")
        graph.add_edge("earnings", "news")
        graph.add_edge("news", "reflection")
        graph.add_edge("reflection", "research")
        graph.add_edge("research", END)
        return graph.compile()

    def _run_sequential(self, state: ResearchGraphState) -> InvestmentReport:
        findings = [
            self.market.run(state["ticker"], state["horizon"]),
            self.company.run(state["ticker"]),
            self.earnings.run(state["ticker"]),
            self.news.run(state["ticker"]),
        ]
        reflection_notes = self.reflection.review(findings)
        return self.research.synthesize(
            state["ticker"],
            state["horizon"],
            state["risk_profile"],
            findings,
            reflection_notes,
        )

    def _append_finding(self, state: ResearchGraphState, finding: AgentFinding) -> ResearchGraphState:
        return {"findings": [*state.get("findings", []), finding]}

    def _run_market(self, state: ResearchGraphState) -> ResearchGraphState:
        return self._append_finding(state, self.market.run(state["ticker"], state["horizon"]))

    def _run_company(self, state: ResearchGraphState) -> ResearchGraphState:
        return self._append_finding(state, self.company.run(state["ticker"]))

    def _run_earnings(self, state: ResearchGraphState) -> ResearchGraphState:
        return self._append_finding(state, self.earnings.run(state["ticker"]))

    def _run_news(self, state: ResearchGraphState) -> ResearchGraphState:
        return self._append_finding(state, self.news.run(state["ticker"]))

    def _run_reflection(self, state: ResearchGraphState) -> ResearchGraphState:
        return {"reflection_notes": self.reflection.review(state.get("findings", []))}

    def _run_research(self, state: ResearchGraphState) -> ResearchGraphState:
        return {
            "report": self.research.synthesize(
                state["ticker"],
                state["horizon"],
                state["risk_profile"],
                state.get("findings", []),
                state["reflection_notes"],
            )
        }
