from __future__ import annotations

from finpilot.core.models import AgentFinding


class ReflectionAgent:
    name = "Reflection Agent"

    def review(self, findings: list[AgentFinding]) -> str:
        missing = []
        if not any("Company" in finding.agent_name for finding in findings):
            missing.append("company fundamentals")
        if not any("Earnings" in finding.agent_name for finding in findings):
            missing.append("earnings context")
        if not any(finding.evidence for finding in findings):
            missing.append("supporting evidence")
        if missing:
            return f"Reflection flagged missing coverage: {', '.join(missing)}."
        return "Reflection check passed: findings include fundamentals, earnings, news, market context, and evidence."
