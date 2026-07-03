# FinPilot Quality Measurement

FinPilot includes an evaluation harness for the project quality requirements.

## Golden dataset

The golden dataset lives at:

```text
data/evaluation/golden_dataset.json
```

It contains 23 hand-curated input/expected-output examples covering:

- RAG methodology questions
- Indian and US stock price questions
- Indian and US stock comparisons
- portfolio/order flows
- market-today flows
- multi-agent research flows
- edge cases and safety cases

Each example includes expected answer keywords, expected route, expected tools, and expected context keywords.

## RAGAS evaluation

Run:

```powershell
.venv\Scripts\python.exe scripts\evaluate_quality.py
```

The report is written to:

```text
reports/evaluation/quality_report.json
reports/evaluation/quality_report.md
```

The RAG pipeline is measured with the required RAGAS metrics:

- faithfulness
- answer relevancy
- context precision
- context recall

The evaluator reports numeric scores for every example and aggregate scores in the summary.

To publish these numbers into Langfuse Scores, run:

```powershell
.venv\Scripts\python.exe scripts\evaluate_quality.py --publish-langfuse
```

This creates a `finpilot.evaluation.quality_report` trace and attaches only the four required Langfuse scores: `ragas_faithfulness`, `ragas_answer_relevance`, `ragas_context_precision`, and `ragas_context_recall`.

## Additional evaluation method

FinPilot also uses trajectory grading. This checks whether each run followed the expected route, used the expected tools, and included required answer content. This is useful for a multi-agent application because a final answer can look correct even if the system skipped RAG, market-data tools, or safety behavior.

## Current baseline

Latest generated baseline:

```text
Golden examples: 23
Pass rate: 100.00%
Golden keyword accuracy: 98.91%
Trajectory quality: 99.64%
RAGAS faithfulness: 84.55%
RAGAS answer relevancy: 69.41%
RAGAS context precision: 68.14%
RAGAS context recall: 88.77%
```

Run the evaluation before shipping changes that affect chat, RAG, research agents, prompts, or tool routing.
