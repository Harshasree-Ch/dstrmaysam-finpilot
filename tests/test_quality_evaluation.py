import json

from finpilot.evaluation import run_quality_evaluation
from finpilot.evaluation.dataset import load_golden_dataset


def test_golden_dataset_has_required_coverage():
    examples = load_golden_dataset()

    assert len(examples) >= 20
    assert any(example.edge_case for example in examples)
    assert {example.category for example in examples} >= {
        "rag_methodology",
        "chat_price",
        "chat_compare",
        "portfolio",
        "research",
        "safety",
    }


def test_quality_evaluation_writes_numeric_report(tmp_path):
    report = run_quality_evaluation(output_dir=tmp_path)
    payload = json.loads(report.output_json.read_text(encoding="utf-8"))

    assert payload["example_count"] >= 20
    assert payload["summary"]["pass_rate"] >= 0.9
    assert 0 <= payload["summary"]["ragas"]["faithfulness"] <= 1
    assert 0 <= payload["summary"]["ragas"]["answer_relevancy"] <= 1
    assert 0 <= payload["summary"]["ragas"]["context_precision"] <= 1
    assert 0 <= payload["summary"]["ragas"]["context_recall"] <= 1
    assert payload["summary"]["trajectory_quality"] >= 0.8


def test_quality_evaluation_can_skip_langfuse_publish(tmp_path):
    report = run_quality_evaluation(output_dir=tmp_path, publish_langfuse=False)

    assert report.output_json.exists()
