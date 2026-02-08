"""Budget-aware selection helpers for retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass

from homllm.retrieval.interfaces import Candidate


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed code/text content."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


@dataclass
class BudgetTracker:
    """Track token usage against an effective context budget."""

    total_budget: int
    reserve: int = 800
    used: int = 0

    @property
    def effective_budget(self) -> int:
        return max(0, self.total_budget - self.reserve)

    @property
    def remaining(self) -> int:
        return max(0, self.effective_budget - self.used)

    def can_add(self, tokens: int) -> bool:
        return (self.used + max(0, tokens)) <= self.effective_budget

    def add(self, tokens: int) -> bool:
        if not self.can_add(tokens):
            return False
        self.used += max(0, tokens)
        return True


def select_candidates_with_budget(
    candidates: list[Candidate],
    total_budget: int,
    reserve: int,
) -> tuple[list[Candidate], BudgetTracker]:
    """
    Select highest-ranked candidates until budget is exhausted.

    Assumes candidates are already sorted by final score descending.
    """
    tracker = BudgetTracker(total_budget=total_budget, reserve=reserve)
    selected: list[Candidate] = []
    for candidate in candidates:
        size = estimate_tokens(candidate.content)
        if tracker.add(size):
            selected.append(candidate)
    return selected, tracker
