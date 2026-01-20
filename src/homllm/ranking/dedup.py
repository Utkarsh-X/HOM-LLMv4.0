"""Deduplication implementation."""

from homllm.retrieval.interfaces import Candidate


class Deduplicator:
    """Deduplicates candidates by content similarity."""

    def deduplicate(
        self, candidates: list[Candidate], similarity_threshold: float = 0.95
    ) -> list[Candidate]:
        """
        Remove duplicate candidates based on content similarity.
        
        Args:
            candidates: List of candidates to deduplicate
            similarity_threshold: Threshold for considering candidates duplicates
        
        Returns:
            Deduplicated list, keeping highest-scoring candidate for each group
        """
        if not candidates:
            return []

        # Sort by final score descending (keep best first)
        sorted_candidates = sorted(
            candidates, key=lambda c: c.hybrid_score, reverse=True
        )

        # Simple deduplication: exact content match
        seen_content: dict[str, Candidate] = {}
        deduplicated = []

        for candidate in sorted_candidates:
            # Use content hash for deduplication
            content_key = candidate.content[:100] if candidate.content else candidate.doc_id

            if content_key not in seen_content:
                seen_content[content_key] = candidate
                deduplicated.append(candidate)
            # Skip if duplicate (already have better-scoring version)

        return deduplicated
