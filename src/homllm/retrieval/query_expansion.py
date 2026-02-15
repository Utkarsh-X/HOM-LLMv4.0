"""Deterministic lexical-only query expansion."""

from __future__ import annotations

import re


class DeterministicQueryExpander:
    """Expand lexical terms using deterministic, config-driven synonyms."""

    def __init__(
        self,
        *,
        enabled: bool,
        max_terms: int,
        min_token_length: int,
        synonyms: dict[str, tuple[str, ...]] | dict[str, list[str]] | dict,
    ):
        self.enabled = bool(enabled)
        self.max_terms = max(0, int(max_terms))
        self.min_token_length = max(1, int(min_token_length))
        self.synonyms = self._normalize_synonyms(synonyms)

    def expand(
        self,
        base_terms: list[str],
    ) -> tuple[list[str], tuple[str, ...]]:
        """
        Expand lexical terms only.

        Returns:
            expanded_terms: base terms + capped expansion terms
            expansion_terms: deterministic expansion terms that were appended
        """
        normalized_base = self._normalize_terms(base_terms)
        if not self.enabled or self.max_terms == 0:
            return normalized_base, ()

        existing = set(normalized_base)
        expansion: list[str] = []

        for term in normalized_base:
            if len(term) < self.min_token_length:
                continue
            for candidate in self.synonyms.get(term, ()):
                if len(candidate) < self.min_token_length:
                    continue
                if candidate in existing:
                    continue
                expansion.append(candidate)
                existing.add(candidate)
                if len(expansion) >= self.max_terms:
                    break
            if len(expansion) >= self.max_terms:
                break

        return normalized_base + expansion, tuple(expansion)

    @staticmethod
    def _normalize_synonyms(raw: dict) -> dict[str, tuple[str, ...]]:
        normalized: dict[str, tuple[str, ...]] = {}
        if not isinstance(raw, dict):
            return normalized
        for key, values in raw.items():
            term = str(key).strip().lower()
            if not term:
                continue
            if not isinstance(values, (list, tuple)):
                continue
            dedup: list[str] = []
            seen: set[str] = set()
            for value in values:
                candidate = str(value).strip().lower()
                if not candidate or candidate == term or candidate in seen:
                    continue
                seen.add(candidate)
                dedup.append(candidate)
            if dedup:
                normalized[term] = tuple(dedup)
        return normalized

    @staticmethod
    def _normalize_terms(terms: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for term in terms:
            candidate = str(term).strip().lower()
            if not candidate:
                continue
            candidate = re.sub(r"[^a-z0-9_]+", "", candidate)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
        return out
