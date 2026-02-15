"""Precision recovery (missing entity detection) implementation."""

import logging
import re
from statistics import mean
from typing import Optional

from homllm.retrieval.interfaces import Candidate, RetrievalConfig

logger = logging.getLogger(__name__)

_STOP_IDENTIFIERS = {
    "if",
    "else",
    "elif",
    "for",
    "while",
    "return",
    "import",
    "from",
    "class",
    "def",
    "true",
    "false",
    "none",
    "self",
    "cls",
    "and",
    "or",
    "not",
    "with",
    "lambda",
    "try",
    "except",
    "finally",
    "raise",
    "assert",
    "pass",
}
_CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_DEF_PATTERN = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_IDENT_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")


class PrecisionRecovery:
    """
    Precision recovery: find referenced-but-missing symbols from retrieved context.

    Contract:
    - Deterministic extraction and insertion order
    - Bounded additions (hard cap <= 5 and ratio <= 20% of merged count)
    - Recovery is config-toggleable
    - Provenance is mandatory for all recovered candidates
    """

    def __init__(
        self,
        bm25_retriever: Optional[object] = None,
        vector_retriever: Optional[object] = None,
    ):
        self.bm25_retriever = bm25_retriever
        self.vector_retriever = vector_retriever
        self.last_metrics: dict[str, float | int] = {}

    def recover(
        self,
        candidates: list[Candidate],
        query: str,
        config: RetrievalConfig,
        max_additions: int = 3,
    ) -> list[Candidate]:
        self.last_metrics = {
            "precision_recovery_added": 0,
            "precision_recovery_cap": 0,
            "precision_recovery_identifiers": 0,
        }
        if not config.precision_recovery_enabled:
            return candidates
        if not candidates:
            return candidates

        ratio_cap = int(len(candidates) * config.precision_recovery_max_ratio)
        hard_cap = min(
            5,
            max(0, int(max_additions)),
            config.precision_recovery_max_additions,
        )
        effective_cap = min(hard_cap, ratio_cap)
        self.last_metrics["precision_recovery_cap"] = effective_cap
        if effective_cap <= 0:
            return candidates

        existing_ids = {candidate.doc_id for candidate in candidates}
        existing_names = self._existing_identifiers(candidates)
        identifiers = self._extract_identifiers(
            candidates,
            query,
            config.precision_recovery_scan_candidates,
            config.precision_recovery_identifier_limit,
        )
        identifiers = [identifier for identifier in identifiers if identifier not in existing_names]
        self.last_metrics["precision_recovery_identifiers"] = len(identifiers)

        recovered: list[tuple[Candidate, float]] = []
        recovered_ids: set[str] = set()
        for identifier in identifiers:
            if len(recovered) >= effective_cap:
                break

            bm25_added = self._recover_from_bm25(
                identifier=identifier,
                seen_ids=existing_ids | recovered_ids,
                config=config,
            )
            if bm25_added:
                candidate, confidence = bm25_added
                recovered.append((candidate, confidence))
                recovered_ids.add(candidate.doc_id)
                if len(recovered) >= effective_cap:
                    break

            vector_added = self._recover_from_vector(
                identifier=identifier,
                seen_ids=existing_ids | recovered_ids,
                config=config,
            )
            if vector_added:
                candidate, confidence = vector_added
                recovered.append((candidate, confidence))
                recovered_ids.add(candidate.doc_id)

        recovered = recovered[:effective_cap]
        if not recovered:
            return candidates

        confidences = [confidence for _, confidence in recovered]
        additions = [candidate for candidate, _ in recovered]
        self.last_metrics.update(
            {
                "precision_recovery_added": len(additions),
                "precision_recovery_conf_min": min(confidences),
                "precision_recovery_conf_max": max(confidences),
                "precision_recovery_conf_mean": mean(confidences),
            }
        )
        logger.info(
            "[PRECISION_RECOVERY] added=%d cap=%d identifiers=%d conf_min=%.3f conf_max=%.3f conf_mean=%.3f",
            len(additions),
            effective_cap,
            len(identifiers),
            min(confidences),
            max(confidences),
            mean(confidences),
        )
        return [*candidates, *additions]

    def _existing_identifiers(self, candidates: list[Candidate]) -> set[str]:
        names: set[str] = set()
        for candidate in candidates:
            if candidate.symbol_id:
                names.add(self._normalize_identifier(candidate.symbol_id))
            for match in _DEF_PATTERN.findall(candidate.content or ""):
                names.add(self._normalize_identifier(match))
        return names

    def _extract_identifiers(
        self,
        candidates: list[Candidate],
        query: str,
        scan_candidates: int,
        identifier_limit: int,
    ) -> list[str]:
        extracted: set[str] = set()
        for candidate in candidates[:scan_candidates]:
            for match in _CALL_PATTERN.findall(candidate.content or ""):
                norm = self._normalize_identifier(match)
                if self._is_candidate_identifier(norm):
                    extracted.add(norm)
        for token in _IDENT_PATTERN.findall(query or ""):
            norm = self._normalize_identifier(token)
            if self._is_candidate_identifier(norm):
                extracted.add(norm)
        return sorted(extracted)[:identifier_limit]

    def _recover_from_bm25(
        self,
        identifier: str,
        seen_ids: set[str],
        config: RetrievalConfig,
    ) -> tuple[Candidate, float] | None:
        if self.bm25_retriever is None:
            return None
        try:
            results = self.bm25_retriever.search(identifier, config.precision_recovery_bm25_top_k)
        except Exception as exc:
            logger.debug("Precision recovery BM25 failed for %s: %s", identifier, exc)
            return None
        ranked = sorted(
            results,
            key=lambda candidate: (-float(candidate.bm25_score), candidate.doc_id),
        )
        for candidate in ranked:
            if candidate.doc_id in seen_ids:
                continue
            if not self._exact_identifier_match(identifier, candidate):
                continue
            confidence = 1.0
            if confidence < config.precision_recovery_min_confidence:
                continue
            return self._with_precision_provenance(candidate, "bm25_exact", identifier), confidence
        return None

    def _recover_from_vector(
        self,
        identifier: str,
        seen_ids: set[str],
        config: RetrievalConfig,
    ) -> tuple[Candidate, float] | None:
        if self.vector_retriever is None:
            return None
        try:
            results = self.vector_retriever.search(
                f"definition {identifier}",
                config.precision_recovery_vector_top_k,
            )
        except Exception as exc:
            logger.debug("Precision recovery vector failed for %s: %s", identifier, exc)
            return None
        ranked = sorted(
            results,
            key=lambda candidate: (-float(candidate.vector_score), candidate.doc_id),
        )
        for candidate in ranked:
            if candidate.doc_id in seen_ids:
                continue
            confidence = float(candidate.vector_score)
            if not self._exact_identifier_match(identifier, candidate):
                confidence = min(confidence, 0.79)
            if confidence < config.precision_recovery_min_confidence:
                continue
            return self._with_precision_provenance(candidate, "vector_semantic", identifier), confidence
        return None

    def _exact_identifier_match(self, identifier: str, candidate: Candidate) -> bool:
        if self._normalize_identifier(candidate.symbol_id or "") == identifier:
            return True
        for match in _DEF_PATTERN.findall(candidate.content or ""):
            if self._normalize_identifier(match) == identifier:
                return True
        return False

    def _with_precision_provenance(
        self,
        candidate: Candidate,
        source: str,
        identifier: str,
    ) -> Candidate:
        provenance_tag = f"precision_recovery:{source}:{identifier}"
        if provenance_tag in candidate.provenance:
            provenance = candidate.provenance
        else:
            provenance = (provenance_tag, *candidate.provenance)
        return Candidate(
            doc_id=candidate.doc_id,
            file=candidate.file,
            symbol_id=candidate.symbol_id,
            content=candidate.content,
            bm25_score=candidate.bm25_score,
            vector_score=candidate.vector_score,
            hybrid_score=candidate.hybrid_score,
            provenance=provenance,
            granularity_level=candidate.granularity_level,
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            parent_symbol_id=candidate.parent_symbol_id,
            entity_ids=candidate.entity_ids,
            doc_type=candidate.doc_type,
            semantic_embedding=candidate.semantic_embedding,
        )

    def _normalize_identifier(self, value: str) -> str:
        if not value:
            return ""
        tail = value.split("::")[-1]
        tail = tail.split(":")[-1]
        tail = tail.split(".")[-1]
        return tail.strip().lower()

    def _is_candidate_identifier(self, identifier: str) -> bool:
        return bool(
            identifier
            and identifier not in _STOP_IDENTIFIERS
            and len(identifier) >= 3
        )
