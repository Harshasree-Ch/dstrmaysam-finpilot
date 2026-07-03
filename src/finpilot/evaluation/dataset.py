from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoldenExample:
    id: str
    category: str
    market: str
    input: str
    expected_answer: str
    expected_keywords: list[str]
    expected_context_keywords: list[str]
    expected_route: str
    expected_tools: list[str]
    edge_case: bool


def load_golden_dataset(path: Path | str = "data/evaluation/golden_dataset.json") -> list[GoldenExample]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GoldenExample(**item) for item in payload]
