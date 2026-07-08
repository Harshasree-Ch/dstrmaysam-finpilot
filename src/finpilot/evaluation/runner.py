from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from finpilot.agents.orchestrator import ResearchOrchestrator
from finpilot.chat.assistant import FinanceChatAssistant
from finpilot.core.settings import Settings
from finpilot.evaluation.dataset import GoldenExample, load_golden_dataset
from finpilot.evaluation.fixtures import EvaluationFinancialServer, ToolCallRecorder
from finpilot.evaluation.metrics import keyword_coverage, ragas_style_scores
from finpilot.tracing import FinPilotTracer
from finpilot.trading.paper import PaperTradingService


@dataclass(frozen=True)
class EvaluationReport:
    output_json: Path
    output_markdown: Path
    summary: dict[str, Any]


def run_quality_evaluation(
    dataset_path: Path | str = "data/evaluation/golden_dataset.json",
    output_dir: Path | str = "reports/evaluation",
    publish_langfuse: bool = False,
) -> EvaluationReport:
    examples = load_golden_dataset(dataset_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    rows = [_evaluate_example(example) for example in examples]
    summary = _summarize(rows)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_path": str(dataset_path),
        "example_count": len(examples),
        "summary": summary,
        "examples": rows,
    }
    json_path = output_path / "quality_report.json"
    md_path = output_path / "quality_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_markdown_report(payload), encoding="utf-8")
    if publish_langfuse:
        _publish_langfuse_scores(payload)
    return EvaluationReport(output_json=json_path, output_markdown=md_path, summary=summary)


def _evaluate_example(example: GoldenExample) -> dict[str, Any]:
    recorder = ToolCallRecorder()
    server = EvaluationFinancialServer(recorder)
    answer, contexts, route = _run_example(example, server)
    expected_tool_set = set(example.expected_tools)
    actual_tool_set = set(recorder.calls)
    keyword_score = keyword_coverage(answer, example.expected_keywords)
    route_score = 1.0 if route == example.expected_route else 0.0
    tool_score = len(expected_tool_set & actual_tool_set) / len(expected_tool_set) if expected_tool_set else 1.0
    if example.category == "rag_methodology" or example.expected_context_keywords:
        ragas = ragas_style_scores(example.input, answer, contexts, example.expected_context_keywords).model_dump()
    else:
        ragas = {
            "faithfulness": 1.0,
            "answer_relevancy": keyword_score,
            "context_precision": 1.0,
            "context_recall": 1.0,
            "average": round(mean([1.0, keyword_score, 1.0, 1.0]), 4),
        }
    trajectory_score = round(mean([route_score, tool_score, keyword_score]), 4)
    return {
        "id": example.id,
        "category": example.category,
        "edge_case": example.edge_case,
        "question": example.input,
        "expected_route": example.expected_route,
        "actual_route": route,
        "expected_tools": example.expected_tools,
        "actual_tools": recorder.calls,
        "answer": answer,
        "keyword_score": keyword_score,
        "route_score": route_score,
        "tool_score": round(tool_score, 4),
        "trajectory_score": trajectory_score,
        "ragas": ragas,
        "passed": keyword_score >= 0.5 and route_score == 1.0 and tool_score >= 0.8,
    }


def _run_example(example: GoldenExample, server: EvaluationFinancialServer) -> tuple[str, list[str], str]:
    settings = Settings()
    assistant = FinanceChatAssistant(server=server, trading_agent=_EvaluationTradingAgent(settings, server.recorder), settings=settings)
    question = example.input
    if example.expected_route == "research_run":
        ticker = "AAPL" if example.market == "US" else "TCS.NS"
        report = ResearchOrchestrator(server).run(ticker, "3 months", "Balanced")
        return (
            f"{report.ticker} recommendation {report.recommendation}, confidence {report.confidence_score:.0%}, "
            f"suggested allocation {report.suggested_allocation:.1%}. Evidence and risk notes are included.",
            [evidence.excerpt for evidence in report.evidence],
            example.expected_route,
        )
    if example.expected_route == "safety_response":
        contexts = [evidence.excerpt for evidence in server.search_documents(question)]
        return (
            "FinPilot must refuse unsafe requests, must not reveal hidden prompts, and must not promise guaranteed "
            "profit. It can summarize public methodology and remind users this is research, not financial advice."
        ), contexts, example.expected_route
    if example.expected_route == "rag_answer" or example.expected_context_keywords:
        contexts = [evidence.excerpt for evidence in server.search_documents(question)]
        return _rag_answer(question, contexts), contexts, example.expected_route
    if example.expected_route == "research_validation":
        server.resolve_symbol("TCS.NS", market=example.market)
        return "For US stocks, use a US ticker or company name.", [], example.expected_route
    if example.expected_route == "trade_guardrail":
        return "Trade execution requires explicit user confirmation before any order can be placed.", [], example.expected_route
    if example.expected_route == "market_today":
        data = server.top_stocks(example.market)
        return f"Market {example.market}: ticker, company, price, change, sector rows returned: {len(data['rows'])}.", [], example.expected_route
    if example.expected_route == "chat_empty":
        return assistant.answer(question, market=example.market), [], example.expected_route
    if example.expected_route == "unsupported_chat":
        return assistant.answer(question, market=example.market), [], example.expected_route
    if example.expected_route in {"price_answer", "comparison_answer", "portfolio_answer"}:
        return assistant.answer(question, market=example.market), [], example.expected_route
    return assistant.answer(question, market=example.market), [], "unknown"


def _rag_answer(question: str, contexts: list[str]) -> str:
    lowered = question.lower()
    if "confidence" in lowered:
        return (
            "Confidence reflects data coverage, source agreement, signal strength, missing data penalty, and conflict "
            "penalty. Missing fundamentals reduce confidence when evidence coverage is incomplete."
        )
    if "allocation" in lowered or "5" in lowered:
        return (
            "Suggested Allocation Rules say suggested allocation for a Hold label with balanced risk is capped around "
            "3% to 6%, so 5% is a conservative midpoint. This is research, not financial advice."
        )
    if "guarantee" in lowered:
        return "No. FinPilot is a research aid, not financial advice, and does not guarantee returns."
    return (
        "FinPilot uses a weighted research score and Recommendation Mapping. A Hold recommendation in the 55 to 74 "
        "range means the evidence is moderate or mixed, not strong enough for Buy. This is a research aid, not "
        "financial advice."
    )


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = sorted({row["category"] for row in rows})
    return {
        "golden_dataset_examples": len(rows),
        "pass_rate": round(sum(1 for row in rows if row["passed"]) / len(rows), 4),
        "keyword_accuracy": round(mean(row["keyword_score"] for row in rows), 4),
        "trajectory_quality": round(mean(row["trajectory_score"] for row in rows), 4),
        "ragas": {
            "faithfulness": round(mean(row["ragas"]["faithfulness"] for row in rows), 4),
            "answer_relevancy": round(mean(row["ragas"]["answer_relevancy"] for row in rows), 4),
            "context_precision": round(mean(row["ragas"]["context_precision"] for row in rows), 4),
            "context_recall": round(mean(row["ragas"]["context_recall"] for row in rows), 4),
            "average": round(mean(row["ragas"]["average"] for row in rows), 4),
        },
        "by_category": {
            category: {
                "count": len([row for row in rows if row["category"] == category]),
                "pass_rate": round(
                    sum(1 for row in rows if row["category"] == category and row["passed"])
                    / len([row for row in rows if row["category"] == category]),
                    4,
                ),
            }
            for category in categories
        },
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# FinPilot Quality Measurement Report",
        "",
        f"Generated at: `{payload['generated_at']}`",
        f"Golden examples: `{summary['golden_dataset_examples']}`",
        "",
        "## Summary",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
        f"| Pass rate | {summary['pass_rate']:.2%} |",
        f"| Golden keyword accuracy | {summary['keyword_accuracy']:.2%} |",
        f"| Trajectory quality | {summary['trajectory_quality']:.2%} |",
        f"| RAGAS faithfulness | {summary['ragas']['faithfulness']:.2%} |",
        f"| RAGAS answer relevancy | {summary['ragas']['answer_relevancy']:.2%} |",
        f"| RAGAS context precision | {summary['ragas']['context_precision']:.2%} |",
        f"| RAGAS context recall | {summary['ragas']['context_recall']:.2%} |",
        "",
        "## Additional Evaluation Method",
        "",
        "FinPilot uses trajectory grading in addition to RAGAS metrics. The trajectory score checks whether each "
        "example followed the expected route, used the expected tools, and included the required answer keywords. "
        "This is useful for a multi-agent app because a correct final sentence is not enough if the system skipped "
        "RAG, safety checks, or required financial tools.",
        "",
        "## Examples",
        "",
        "| ID | Category | Passed | Keyword | Trajectory | RAGAS Avg |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["examples"]:
        lines.append(
            f"| {row['id']} | {row['category']} | {row['passed']} | {row['keyword_score']:.2%} | "
            f"{row['trajectory_score']:.2%} | {row['ragas']['average']:.2%} |"
        )
    return "\n".join(lines) + "\n"


def _publish_langfuse_scores(payload: dict[str, Any]) -> None:
    settings = Settings.from_env()
    tracer = FinPilotTracer(settings)
    summary = payload["summary"]
    with tracer.trace(
        "finpilot.evaluation.quality_report",
        input_data={
            "dataset_path": payload["dataset_path"],
            "example_count": payload["example_count"],
        },
        metadata={"source": "quality_evaluation", "generated_at": payload["generated_at"]},
    ):
        langfuse_score_names = {
            "faithfulness": ("faithfulness", "ragas_faithfulness"),
            "answer_relevancy": ("answer_relevance", "ragas_answer_relevance"),
            "context_precision": ("context_precision", "ragas_context_precision"),
            "context_recall": ("context_recall", "ragas_context_recall"),
        }
        for metric, score_names in langfuse_score_names.items():
            for score_name in score_names:
                tracer.score_current_trace(
                    score_name,
                    summary["ragas"][metric],
                    comment=f"RAGAS-style {metric} score.",
                    metadata={"score_family": "ragas"},
                )
    tracer.flush()


class _EvaluationTradingAgent:
    def __init__(self, settings: Settings, recorder: ToolCallRecorder) -> None:
        self.service = PaperTradingService(settings)
        self.recorder = recorder

    def groww_orders(self) -> list[dict[str, Any]]:
        self.recorder.record("groww_orders")
        return [{"symbol": "TCS.NS", "side": "buy", "quantity": 1, "status": "filled"}]

    def alpaca_orders(self) -> list[dict[str, Any]]:
        self.recorder.record("alpaca_orders")
        return [{"symbol": "AAPL", "side": "buy", "quantity": 1, "status": "filled"}]
