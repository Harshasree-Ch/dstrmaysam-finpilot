from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from finpilot.evaluation import run_quality_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FinPilot golden dataset, RAGAS, and trajectory evaluations.")
    parser.add_argument("--dataset", default="data/evaluation/golden_dataset.json")
    parser.add_argument("--output-dir", default="reports/evaluation")
    parser.add_argument("--publish-langfuse", action="store_true", help="Publish aggregate and case scores to Langfuse.")
    args = parser.parse_args()
    report = run_quality_evaluation(args.dataset, args.output_dir, publish_langfuse=args.publish_langfuse)
    print(f"Wrote {report.output_json}")
    print(f"Wrote {report.output_markdown}")
    print(report.summary)


if __name__ == "__main__":
    main()
