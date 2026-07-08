from __future__ import annotations

import json
import time

from finpilot.core.models import AgentFinding, Evidence, InvestmentReport
from finpilot.core.settings import Settings
from finpilot.observability import log_event
from finpilot.prompts import load_prompt
from finpilot.tracing import FinPilotTracer


class InvestmentResearchAgent:
    name = "Investment Research Agent"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def synthesize(
        self,
        ticker: str,
        horizon: str,
        risk_profile: str,
        findings: list[AgentFinding],
        reflection_notes: str,
    ) -> InvestmentReport:
        market_score = next(
            (finding.score for finding in findings if finding.agent_name == "Market Performance Agent"),
            0.0,
        )
        other_scores = [finding.score for finding in findings if finding.agent_name != "Market Performance Agent"]
        supporting_score = sum(other_scores) / max(len(other_scores), 1)
        aggregate_score = (market_score * 0.55) + (supporting_score * 0.45)
        recommendation = self._recommendation(aggregate_score)
        allocation = 0.08 if risk_profile in {"Growth", "Aggressive"} else 0.05
        confidence = min(0.92, 0.62 + abs(aggregate_score) * 0.4)
        evidence: list[Evidence] = []
        for finding in findings:
            evidence.extend(finding.evidence)
        report = InvestmentReport(
            ticker=ticker,
            title=f"{ticker} Investment Research Report",
            recommendation=recommendation,
            investment_summary=(
                f"For a {horizon} horizon and {risk_profile.lower()} risk profile, FinPilot rates {ticker} as "
                f"{recommendation}. The conclusion blends price performance, company quality, earnings context, "
                "and recent news flow. This is a research aid, not financial advice."
            ),
            strengths=[
                "Durable business model and defensible market position.",
                "Evidence-backed earnings and document review support the core thesis.",
                "Recent ticker-specific news is monitored separately from fundamentals.",
            ],
            risks=[
                "Macro, regulation, valuation, and competitive pressure may weaken the thesis.",
                "Live market data can be delayed or temporarily unavailable depending on the upstream provider.",
                "Position sizing and concentration should be reviewed before increasing exposure.",
            ],
            evidence=evidence,
            agent_findings=findings,
            suggested_allocation=allocation,
            confidence_score=confidence,
            reflection_notes=reflection_notes,
        )
        return self._bedrock_enrich_report(report, findings, horizon, risk_profile)

    def _recommendation(self, score: float) -> str:
        if score >= 0.42:
            return "Buy"
        if score >= 0.18:
            return "Accumulate"
        if score >= -0.20:
            return "Hold"
        if score >= -0.40:
            return "Watch"
        return "Avoid"

    def _bedrock_enrich_report(
        self,
        report: InvestmentReport,
        findings: list[AgentFinding],
        horizon: str,
        risk_profile: str,
    ) -> InvestmentReport:
        if not self.settings.use_bedrock:
            return report
        try:
            payload = self._invoke_bedrock(report, findings, horizon, risk_profile)
        except Exception as exc:
            return report.model_copy(
                update={
                    "reflection_notes": (
                        f"{report.reflection_notes} Bedrock synthesis was unavailable, "
                        f"so FinPilot used deterministic synthesis. Reason: {exc}"
                    )
                }
            )

        return report.model_copy(
            update={
                "investment_summary": payload.get("investment_summary") or report.investment_summary,
                "strengths": payload.get("strengths") or report.strengths,
                "risks": payload.get("risks") or report.risks,
                "reflection_notes": payload.get("reflection_notes") or report.reflection_notes,
            }
        )

    def _invoke_bedrock(
        self,
        report: InvestmentReport,
        findings: list[AgentFinding],
        horizon: str,
        risk_profile: str,
    ) -> dict:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=self.settings.aws_region)
        prompt_template = load_prompt("research_synthesis", self.settings.prompt_version)
        prompt = {
            "task": prompt_template.task,
            "rules": prompt_template.rules,
            "output_schema": prompt_template.output_schema,
            "ticker": report.ticker,
            "horizon": horizon,
            "risk_profile": risk_profile,
            "recommendation": report.recommendation,
            "confidence_score": report.confidence_score,
            "suggested_allocation": report.suggested_allocation,
            "agent_findings": [
                {
                    "agent": finding.agent_name,
                    "headline": finding.headline,
                    "summary": finding.summary,
                    "score": finding.score,
                    "evidence": [
                        {
                            "source": evidence.source,
                            "title": evidence.title,
                            "excerpt": evidence.excerpt,
                            "url": evidence.url,
                        }
                        for evidence in finding.evidence[:3]
                    ],
                }
                for finding in findings
            ],
        }
        user_message = prompt_template.render_user_message(prompt)
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 900,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt_template.system}\n\n{user_message}",
                }
            ],
        }
        tracer = FinPilotTracer(self.settings)
        langfuse_prompt = tracer.sync_prompt(
            name=prompt_template.name,
            version_label=prompt_template.version,
            system=prompt_template.system,
            user_template=prompt_template.task,
            config={
                "rules": prompt_template.rules,
                "output_schema": prompt_template.output_schema,
                "model": self.settings.bedrock_model_id,
                "temperature": request_body["temperature"],
                "max_tokens": request_body["max_tokens"],
            },
        )
        start = time.perf_counter()
        response = client.invoke_model(
            modelId=self.settings.bedrock_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body),
        )
        latency_ms = (time.perf_counter() - start) * 1000
        body = json.loads(response["body"].read())
        text = body["content"][0]["text"]
        usage = body.get("usage", {})
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0
        cost_details = self._estimated_llm_cost_details(input_tokens, output_tokens)
        estimated_cost_usd = cost_details["total"]
        log_event(
            "finpilot_llm_call",
            {
                "agent": self.name,
                "provider": "aws-bedrock",
                "model": self.settings.bedrock_model_id,
                "prompt_name": prompt_template.name,
                "prompt_version": prompt_template.version,
                "latency_ms": round(latency_ms, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": estimated_cost_usd,
                "cost_per_query_usd": estimated_cost_usd,
                "input_cost_usd": cost_details["input"],
                "output_cost_usd": cost_details["output"],
            },
            self.settings,
        )
        with tracer.trace(
            "finpilot.llm.research_synthesis",
            input_data=prompt,
            metadata={
                "agent": self.name,
                "ticker": report.ticker,
                "prompt_name": prompt_template.name,
                "prompt_version": prompt_template.version,
            },
        ) as trace:
            tracer.generation(
                trace=trace,
                name="bedrock_research_synthesis",
                model=self.settings.bedrock_model_id,
                prompt=request_body,
                completion=text,
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                latency_ms=latency_ms,
                cost_details=cost_details if estimated_cost_usd else None,
                prompt_client=langfuse_prompt,
                version=prompt_template.version,
                metadata={
                    "provider": "aws-bedrock",
                    "prompt_name": prompt_template.name,
                    "prompt_version": prompt_template.version,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "input_cost_usd": cost_details["input"],
                    "output_cost_usd": cost_details["output"],
                    "estimated_cost_usd": estimated_cost_usd,
                    "cost_per_query_usd": estimated_cost_usd,
                },
            )
        return json.loads(text)

    def _estimated_llm_cost_details(self, input_tokens: int, output_tokens: int) -> dict[str, float]:
        input_cost = (input_tokens / 1000) * self.settings.llm_input_cost_per_1k_usd
        output_cost = (output_tokens / 1000) * self.settings.llm_output_cost_per_1k_usd
        return {
            "input": round(input_cost, 6),
            "output": round(output_cost, 6),
            "total": round(input_cost + output_cost, 6),
        }
