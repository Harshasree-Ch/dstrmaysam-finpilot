from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class RagasScores:
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float

    @property
    def average(self) -> float:
        return round(mean([self.faithfulness, self.answer_relevancy, self.context_precision, self.context_recall]), 4)

    def model_dump(self) -> dict[str, float]:
        return {
            "faithfulness": self.faithfulness,
            "answer_relevancy": self.answer_relevancy,
            "context_precision": self.context_precision,
            "context_recall": self.context_recall,
            "average": self.average,
        }


def keyword_coverage(text: str, expected_keywords: Iterable[str]) -> float:
    keywords = list(expected_keywords)
    if not keywords:
        return 1.0
    normalized = _normalize(text)
    hits = sum(1 for keyword in keywords if _normalize(keyword) in normalized)
    return round(hits / len(keywords), 4)


def ragas_style_scores(question: str, answer: str, contexts: list[str], expected_context_keywords: list[str]) -> RagasScores:
    context_text = " ".join(contexts)
    answer_terms = _content_terms(answer)
    context_terms = _content_terms(context_text)
    question_terms = _content_terms(question)
    expected_terms = _content_terms(" ".join(expected_context_keywords))

    faithfulness = _overlap(answer_terms, context_terms) if contexts else 0.0
    answer_relevancy = _overlap(answer_terms, question_terms | expected_terms)
    context_precision = _overlap(context_terms, answer_terms | expected_terms) if contexts else 0.0
    context_recall = keyword_coverage(context_text, expected_context_keywords)
    return RagasScores(
        faithfulness=round(faithfulness, 4),
        answer_relevancy=round(answer_relevancy, 4),
        context_precision=round(context_precision, 4),
        context_recall=round(context_recall, 4),
    )


def _overlap(actual: set[str], expected: set[str]) -> float:
    if not actual or not expected:
        return 0.0
    return len(actual & expected) / len(actual)


def _content_terms(text: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "not",
        "of",
        "or",
        "the",
        "to",
        "with",
    }
    return {term for term in re.findall(r"[a-z0-9%]+", _normalize(text)) if len(term) > 2 and term not in stopwords}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
