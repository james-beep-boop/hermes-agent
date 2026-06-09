"""Heuristic scoring for local-model 'smarts' comparisons.

The goal is not to measure raw token output quality; it is to rank how well a
model handles the kinds of instructions we care about locally:
- follow hard constraints
- avoid forbidden detours
- ask for missing context instead of hallucinating
- stay concise when the prompt asks for it

This intentionally stays lightweight so it can score existing rerun artifacts
and synthetic fixtures without needing a live model endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import re
from typing import Iterable, Sequence


@dataclass(frozen=True)
class SmartsRow:
    test_id: str
    prompt_name: str
    finish_reason: str
    shape: str
    content_preview: str


@dataclass(frozen=True)
class ModelSmartsSummary:
    model_name: str
    model_label: str
    endpoint: str
    score: float
    row_count: int


@dataclass(frozen=True)
class SmartsArtifactReport:
    path: str
    format: str
    rows: list[SmartsRow]
    models: list[ModelSmartsSummary]


def _has_numbered_list(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*\d+[.)]\s+", text))


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _score_ordered_planning(text: str) -> float:
    score = 0.0
    if _has_numbered_list(text):
        score += 0.35
    if _contains_any(text, ["evening", "spending", "30 minutes", "free time", "free"]):
        score += 0.35
    if len(text.strip()) < 280:
        score += 0.15
    return min(score, 1.0)


def _score_negative_constraint(text: str) -> float:
    lower = text.lower()
    forbidden = ["coding", "deployment", "multimodal", "multimodal tests"]
    if any(term in lower for term in forbidden):
        return 0.0
    score = 0.4
    if _contains_any(text, ["reasoning", "planning", "agentic use", "evaluate"]):
        score += 0.35
    if len(text.strip()) < 260:
        score += 0.15
    return min(score, 1.0)


def _score_missing_context(text: str) -> float:
    lower = text.lower()
    if _contains_any(lower, ["please provide", "i need", "missing", "provide the situation", "provide the context"]):
        return 1.0
    if _contains_any(lower, ["summary", "summarize", "context"]):
        return 0.45
    return 0.1


def _score_constraint_tracking(text: str) -> float:
    score = 0.0
    if _contains_any(text, ["original", "constraint", "priority", "conflict", "preserve"]):
        score += 0.45
    if _contains_any(text, ["ignore", "follow", "stay centered", "restate", "hard constraint"]):
        score += 0.35
    if len(text.strip()) < 280:
        score += 0.1
    return min(score, 1.0)


def _score_generic(text: str) -> float:
    score = 0.2
    if _has_numbered_list(text) or _contains_any(text, ["- ", "* "]):
        score += 0.2
    if len(text.strip()) < 320:
        score += 0.2
    if _contains_any(text, ["please provide", "i cannot", "cannot", "understood", "here is"]):
        score += 0.15
    return min(score, 1.0)


def score_row(row: SmartsRow) -> float:
    """Return a 0..1 smartness score for a single benchmark row."""

    score = 0.0

    if row.finish_reason == "stop":
        score += 0.35
    elif row.finish_reason == "length":
        score += 0.05

    if row.shape == "content_only":
        score += 0.15
    elif row.shape == "reasoning_plus_content":
        score += 0.1

    text = (row.content_preview or "").strip()
    if not text:
        return score

    prompt = row.prompt_name.lower()
    if "ordered planning under constraints" in prompt:
        score += _score_ordered_planning(text)
    elif "follow the negative constraint" in prompt:
        score += _score_negative_constraint(text)
    elif "focused summarization" in prompt:
        score += _score_missing_context(text)
    elif "ignore distractors" in prompt or "stay centered" in prompt:
        score += _score_constraint_tracking(text)
    elif "re-anchor after interruption" in prompt:
        score += 0.25 if _contains_any(text, ["original goal", "restate", "continue"]) else 0.0
        score += 0.25 if len(text.strip()) < 260 else 0.0
    elif "constraint conflict" in prompt or "conflict resolution" in prompt:
        score += 0.35 if _contains_any(text, ["hard constraint", "takes priority", "prioritize", "conflict"]) else 0.0
        score += 0.25 if len(text.strip()) < 260 else 0.0
    elif "stability under noise" in prompt:
        score += 0.35 if _contains_any(text, ["irrelevant", "noise", "false leads", "ignore"]) else 0.0
        score += 0.25 if len(text.strip()) < 260 else 0.0
    else:
        score += _score_generic(text)

    return round(min(score, 1.0), 4)


def score_run(rows: Iterable[SmartsRow]) -> float:
    rows = list(rows)
    if not rows:
        return 0.0
    return round(sum(score_row(row) for row in rows) / len(rows), 4)


def _rows_from_csv(path: Path) -> tuple[list[SmartsRow], list[ModelSmartsSummary]]:
    by_model: dict[tuple[str, str, str], list[SmartsRow]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            model_name = raw.get("model_name") or ""
            model_label = raw.get("model_label") or ""
            endpoint = raw.get("endpoint") or ""
            key = (model_name, model_label, endpoint)
            by_model.setdefault(key, []).append(
                SmartsRow(
                    test_id=raw.get("test_id") or "",
                    prompt_name=raw.get("prompt_name") or "",
                    finish_reason=raw.get("finish_reason") or "",
                    shape=raw.get("shape") or "",
                    content_preview=raw.get("content_preview") or "",
                )
            )
    rows = [row for group in by_model.values() for row in group]
    models = [
        ModelSmartsSummary(
            model_name=model_name,
            model_label=model_label,
            endpoint=endpoint,
            score=score_run(group),
            row_count=len(group),
        )
        for (model_name, model_label, endpoint), group in by_model.items()
    ]
    models.sort(key=lambda item: (-item.score, item.model_name, item.model_label))
    return rows, models


def _rows_from_raw_json(path: Path) -> tuple[list[SmartsRow], list[ModelSmartsSummary]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[SmartsRow] = []
    models: list[ModelSmartsSummary] = []
    for model in data.get("models", []):
        tests = model.get("tests", [])
        model_rows = [
            SmartsRow(
                test_id=test.get("test_id") or "",
                prompt_name=test.get("prompt_name") or "",
                finish_reason=test.get("finish_reason") or "",
                shape=test.get("shape") or "",
                content_preview=test.get("content_preview") or "",
            )
            for test in tests
        ]
        rows.extend(model_rows)
        models.append(
            ModelSmartsSummary(
                model_name=model.get("name") or "",
                model_label=model.get("label") or "",
                endpoint=model.get("endpoint") or "",
                score=score_run(model_rows),
                row_count=len(model_rows),
            )
        )
    models.sort(key=lambda item: (-item.score, item.model_name, item.model_label))
    return rows, models


def score_artifact(path: str | Path) -> SmartsArtifactReport:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows, models = _rows_from_csv(path)
        return SmartsArtifactReport(path=str(path), format="csv", rows=rows, models=models)
    if suffix == ".json":
        rows, models = _rows_from_raw_json(path)
        return SmartsArtifactReport(path=str(path), format="json", rows=rows, models=models)
    raise ValueError(f"Unsupported artifact format for {path}")


def score_artifacts(paths: Sequence[str | Path]) -> list[SmartsArtifactReport]:
    return [score_artifact(path) for path in paths]
