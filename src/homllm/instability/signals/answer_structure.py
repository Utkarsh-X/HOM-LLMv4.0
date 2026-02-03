"""
Answer-Structure Variance (spec § Signal 5).

Token count, section/header count, code block presence, list density, refusal markers.
Stable context + high structure variance → UNSTABLE_REASONING.
"""

from __future__ import annotations

import re

from homllm.instability.constants import REFUSAL_MARKERS
from homllm.instability.interfaces import PrimaryLabelType, RunRecord
from homllm.instability.utils import normalized_variance


def _token_count(text: str) -> int:
    return len(text.split())


def _section_count(text: str) -> int:
    return len(re.findall(r"^#{1,6}\s+\w", text, re.MULTILINE)) + len(
        re.findall(r"^[\w\s]+\n[-=]{2,}\s*$", text, re.MULTILINE)
    )


def _has_code_block(text: str) -> float:
    return 1.0 if ("```" in text or "    " in text) else 0.0


def _list_density(text: str) -> float:
    lines = text.strip().split("\n")
    if not lines:
        return 0.0
    list_lines = sum(1 for L in lines if re.match(r"^\s*[-*]\s+", L) or re.match(r"^\s*\d+\.\s+", L))
    return list_lines / len(lines)


def _refusal_count(text: str) -> int:
    lower = text.lower()
    return sum(1 for m in REFUSAL_MARKERS if m in lower)


def answer_structure_variance(runs: tuple[RunRecord, ...]) -> tuple[float, PrimaryLabelType | None]:
    """
    Instability from variance in answer structure across runs.
    High variance → UNSTABLE_REASONING (stable context + oscillating structure).
    """
    if len(runs) < 2:
        return 0.0, None
    tokens = tuple(float(_token_count(r.answer_text)) for r in runs)
    sections = tuple(float(_section_count(r.answer_text)) for r in runs)
    code = tuple(_has_code_block(r.answer_text) for r in runs)
    lists = tuple(_list_density(r.answer_text) for r in runs)
    refusals = tuple(float(_refusal_count(r.answer_text)) for r in runs)
    v_tok = normalized_variance(tokens)
    v_sec = normalized_variance(sections)
    v_code = normalized_variance(code)
    v_list = normalized_variance(lists)
    v_ref = normalized_variance(refusals)
    score = min(1.0, (v_tok + v_sec + v_code + v_list + v_ref) / 5.0)
    label: PrimaryLabelType | None = "UNSTABLE_REASONING" if score > 0.5 else None
    return score, label
