"""Coverage recovery (missing domain coverage) implementation."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional

from homllm.retrieval.interfaces import Candidate, RetrievalConfig

logger = logging.getLogger(__name__)

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "database": ("database", "db", "sql", "sqlite", "postgres", "pool", "connection"),
    "cache": ("cache", "redis", "ttl", "lru", "lfu"),
    "monitoring": ("metrics", "histogram", "percentile", "latency", "p95", "p99", "timer", "trace", "tracing"),
    "optimization": ("optimizer", "optimization", "plan", "planner", "join", "cost"),
    "security": ("auth", "jwt", "token", "permission"),
    "async_jobs": ("job", "queue", "worker", "retry", "batch"),
    "search": ("search", "ranking", "rerank", "similarity", "embedding", "index"),
    "api": ("api", "endpoint", "route", "http"),
}

_DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "database": ("database/",),
    "cache": ("cache/",),
    "monitoring": ("monitoring/",),
    "optimization": ("optimization/",),
    "security": ("security/",),
    "async_jobs": ("async_jobs/",),
    "search": ("search_engine/",),
    "api": ("api/",),
}


class CoverageRecovery:
    """
    Coverage recovery: add candidates from missing system domains inferred from the query.

    Contract:
    - Deterministic, bounded additions
    - No hardcoded filenames
    - Provenance tagged per domain
    """

    def __init__(
        self,
        bm25_retriever: Optional[object] = None,
        vector_retriever: Optional[object] = None,
    ):
        self.bm25_retriever = bm25_retriever
        self.vector_retriever = vector_retriever
        self.last_metrics: dict[str, object] = {}

    def recover(
        self,
        candidates: list[Candidate],
        query: str,
        lexical_terms: list[str],
        config: RetrievalConfig,
        max_additions: int = 3,
    ) -> list[Candidate]:
        self.last_metrics = {
            "coverage_recovery_added": 0,
            "coverage_recovery_cap": 0,
            "coverage_recovery_missing_domains": [],
            "coverage_recovery_domains_considered": [],
        }
        if not config.coverage_recovery_enabled:
            return candidates
        if not candidates:
            return candidates

        desired_domains = self._infer_domains(query)
        self.last_metrics["coverage_recovery_domains_considered"] = sorted(desired_domains)
        if not desired_domains:
            return candidates

        covered_domains = {
            domain
            for domain in (self._domain_for_file(c.file) for c in candidates)
            if domain
            if self._candidate_has_domain_signal(candidates, domain)
        }
        missing_domains = [d for d in sorted(desired_domains) if d not in covered_domains]
        self.last_metrics["coverage_recovery_missing_domains"] = missing_domains
        if not missing_domains:
            return candidates

        ratio_cap = int(len(candidates) * config.coverage_recovery_max_ratio)
        hard_cap = min(
            5,
            max(0, int(max_additions)),
            config.coverage_recovery_max_additions,
        )
        effective_cap = min(hard_cap, ratio_cap)
        self.last_metrics["coverage_recovery_cap"] = effective_cap
        if effective_cap <= 0:
            return candidates

        existing_ids = {candidate.doc_id for candidate in candidates}
        additions: list[Candidate] = []

        for domain in missing_domains:
            if len(additions) >= effective_cap:
                break
            recovered = self._recover_domain(
                domain=domain,
                query=query,
                lexical_terms=lexical_terms,
                seen_ids=existing_ids,
                config=config,
            )
            if recovered is None:
                continue
            additions.append(recovered)
            existing_ids.add(recovered.doc_id)

        if not additions:
            return candidates

        self.last_metrics["coverage_recovery_added"] = len(additions)
        logger.info(
            "[COVERAGE_RECOVERY] added=%d cap=%d missing=%s",
            len(additions),
            effective_cap,
            ",".join(missing_domains),
        )
        return [*candidates, *additions]

    def _recover_domain(
        self,
        domain: str,
        query: str,
        lexical_terms: list[str],
        seen_ids: set[str],
        config: RetrievalConfig,
    ) -> Candidate | None:
        if self.bm25_retriever is None:
            return None

        domain_terms = list(_DOMAIN_KEYWORDS.get(domain, ()))
        query_terms = list(lexical_terms or [])
        combined = []
        for term in [*domain_terms, *query_terms]:
            t = str(term).strip().lower()
            if not t or t in combined:
                continue
            combined.append(t)
            if len(combined) >= 16:
                break
        search_query = " ".join(combined) if combined else (query or domain)

        try:
            results = self.bm25_retriever.search(
                search_query, config.coverage_recovery_bm25_top_k
            )
        except Exception as exc:
            logger.debug("Coverage recovery BM25 failed for %s: %s", domain, exc)
            return None
        if not results:
            return None

        ranked = sorted(
            results,
            key=lambda candidate: (-float(candidate.bm25_score), candidate.doc_id),
        )
        for candidate in ranked:
            if candidate.doc_id in seen_ids:
                continue
            if self._domain_for_file(candidate.file) != domain:
                continue
            provenance = tuple(candidate.provenance or ()) + (f"coverage_recovery:{domain}",)
            return replace(candidate, provenance=provenance)
        return None

    @staticmethod
    def _candidate_has_domain_signal(candidates: list[Candidate], domain: str) -> bool:
        keywords = _DOMAIN_KEYWORDS.get(domain, ())
        if not keywords:
            return False
        for candidate in candidates:
            if CoverageRecovery._domain_for_file(candidate.file) != domain:
                continue
            content = (candidate.content or "").lower()
            if not content:
                continue
            for keyword in keywords:
                if keyword in content:
                    return True
        return False

    @staticmethod
    def _domain_for_file(file_path: str | None) -> str | None:
        if not file_path:
            return None
        norm = file_path.replace("\\", "/")
        for domain, prefixes in _DOMAIN_PREFIXES.items():
            for prefix in prefixes:
                if norm.startswith(prefix):
                    return domain
        return None

    @staticmethod
    def _infer_domains(query: str) -> set[str]:
        text = (query or "").lower()
        domains: set[str] = set()
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    domains.add(domain)
                    break
        return domains
