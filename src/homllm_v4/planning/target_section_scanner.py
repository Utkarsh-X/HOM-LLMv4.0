"""Target-file section scanning for the edit proposer.

When retrieval does not return evidence for the file the agent must edit
(``target_evidence_retrieved: false``), the planner previously fell back to a
single candidate holding the *entire* file. The evidence renderer then
truncated that blob to its first few thousand characters — almost always the
import header — so the model saw no pointer to the section that actually
contains the bug.

This module replaces that with a deterministic section scan: it splits the
target file into overlapping line windows, scores each window by lexical
relevance to the task query + edit intent + expected behavior (with a bonus
for ``def``/``class`` lines), and emits the top non-overlapping windows as
evidence candidates with real line spans. The model then sees something like
``[target-section-2] complexes.py:590-660`` with the actual code, instead of
a truncated file header.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_STOPWORDS = frozenset(
    """
    a an and are as at be by for from in is it of on or that the this to
    with will would should when what which who whom whose why how where there
    their they them its it's not no nor but so if then else than too very
    all any both each few more most other some such only own same
    your you we us our
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class TargetSection:
    """A scored line window of the target file (1-based, inclusive span)."""

    span_start: int
    span_end: int
    content: str
    score: float


def significant_tokens(*texts: str) -> frozenset[str]:
    """Lowercased alphanumeric/underscore tokens from the given texts.

    Drops stopwords and tokens shorter than 3 characters.
    """
    tokens: set[str] = set()
    for text in texts:
        for word in _WORD_RE.findall(text.lower()):
            if len(word) >= 3 and word not in _STOPWORDS:
                tokens.add(word)
    return frozenset(tokens)


def scan_target_sections(
    content: str,
    *,
    query: str,
    context: str = "",
    window_lines: int = 80,
    step_lines: int = 20,
    max_sections: int = 3,
    min_score: float = 1.0,
    max_overlap_ratio: float = 0.5,
) -> tuple[TargetSection, ...]:
    """Return the top non-overlapping query-relevant sections of ``content``.

    Args:
        content: Full text of the target file.
        query: Task query (the SWE-bench problem statement).
        context: Extra signal (edit intent + expected behavior).
        window_lines: Lines per window.
        step_lines: Window stride (windows overlap).
        max_sections: Maximum sections to return.
        min_score: Minimum lexical score for a window to be kept.
        max_overlap_ratio: Reject a candidate whose line range overlaps an
            already-accepted section by more than this ratio.
    """
    lines = content.splitlines()
    if not lines:
        return ()
    tokens = significant_tokens(query, context)
    if not tokens:
        return ()

    window_lines = max(1, int(window_lines))
    step_lines = max(1, int(step_lines))
    scan_start = _first_code_line(lines)
    windows: list[tuple[int, int, str]] = []
    for start in range(scan_start, len(lines), step_lines):
        end = min(start + window_lines, len(lines))
        windows.append((start, end, "\n".join(lines[start:end])))
    idf = _window_idf(windows, tokens)
    scored: list[tuple[float, int, int, str]] = []
    for start, end, window_text in windows:
        score = _score_window(window_text, tokens, idf)
        if score >= min_score:
            scored.append((score, start, end, window_text))

    if not scored:
        return ()

    scored.sort(key=lambda item: (-item[0], item[1]))
    accepted: list[tuple[int, int, str, float]] = []
    for score, start, end, window_text in scored:
        if len(accepted) >= max_sections:
            break
        if _overlaps_any(start, end, accepted, max_overlap_ratio):
            continue
        accepted.append((start, end, window_text, score))

    accepted.sort(key=lambda item: item[0])
    return tuple(
        TargetSection(
            span_start=start + 1,
            span_end=end,
            content=window_text,
            score=score,
        )
        for start, end, window_text, score in accepted
    )


def _window_idf(
    windows: list[tuple[int, int, str]],
    tokens: frozenset[str],
) -> dict[str, float]:
    """Inverse document frequency per token across the file's windows.

    Generic words like "expr" or "error" appear in almost every method
    signature/docstring; weighting by inverse window frequency makes the rare
    words that actually discriminate the buggy region (e.g. ``conjugate``)
    dominate the score.
    """
    n = max(1, len(windows))
    df: dict[str, int] = {token: 0 for token in tokens}
    for _start, _end, text in windows:
        lower = text.lower()
        seen: set[str] = set()
        for token in tokens:
            if token in seen:
                continue
            if re.search(r"\b" + re.escape(token) + r"\b", lower):
                df[token] += 1
                seen.add(token)
    return {token: 1.0 + math.log(n / (1 + df[token])) for token in tokens}


def _score_window(
    text: str,
    tokens: frozenset[str],
    idf: dict[str, float],
) -> float:
    lower = text.lower()
    score = 0.0
    for token in tokens:
        pattern = r"\b" + re.escape(token) + r"\b"
        score += len(re.findall(pattern, lower)) * idf[token]
    if score <= 0:
        # No query signal at all: a def/class bonus alone must not rescue a
        # window into the evidence (that is how zero-relevance regions like
        # import headers creep in).
        return 0.0
    # Structural bonus: function/class boundaries are where fixes live, so
    # code-dense regions should beat prose-heavy (docstring) regions even when
    # the docstrings repeat generic query words like "expression" or "error".
    def_class_lines = 0
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("def ", "class ", "async def ")):
            def_class_lines += 1
            for token in tokens:
                if re.search(r"\b" + re.escape(token) + r"\b", stripped):
                    score += 2.0 * idf[token]
    score += 1.0 * def_class_lines
    return score


def _first_code_line(lines: list[str]) -> int:
    """Index of the first real code line, skipping imports/module docstring.

    The file header (imports and a long module docstring) is rarely where a
    fix lives, and it tends to score high because docstrings repeat generic
    words. Scanning starts at the first ``def``/``class``/decorator, with a
    small lookback so decorators (``@property``) stay attached.
    """
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "async def ", "@")):
            lookback = 0
            while lookback < 3 and index - lookback - 1 >= 0:
                previous = lines[index - lookback - 1].strip()
                if previous.startswith("@"):
                    lookback += 1
                else:
                    break
            return max(0, index - lookback)
    return 0


def _overlaps_any(
    start: int,
    end: int,
    accepted: list[tuple[int, int, str, float]],
    max_overlap_ratio: float,
) -> bool:
    window_len = max(1, end - start)
    for acc_start, acc_end, _acc_text, _acc_score in accepted:
        overlap = max(0, min(end, acc_end) - max(start, acc_start))
        if overlap / window_len > max_overlap_ratio:
            return True
    return False
