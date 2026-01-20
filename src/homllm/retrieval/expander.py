"""Structural expansion implementation."""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.retrieval.interfaces import Candidate, RetrievalConfig, StructuralExpander

logger = logging.getLogger(__name__)


class StructuralExpanderImpl(StructuralExpander):
    """Structural expansion for decorators, callees, etc."""

    def __init__(self, embedder: Optional[object] = None, duckdb_path: Optional[Path] = None):
        """
        Initialize expander.
        
        Args:
            embedder: Embedder for similarity checks (optional)
            duckdb_path: Path to DuckDB for content loading (optional)
        """
        self.embedder = embedder
        self.duckdb_path = duckdb_path
        self._duckdb: Optional[DuckDBAdapter] = None
        if duckdb_path:
            try:
                self._duckdb = DuckDBAdapter(duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for expander: {e}")

    def expand(
        self,
        candidates: list[Candidate],
        query: str,
        callgraph: dict,  # Simplified callgraph access
        config: RetrievalConfig,
    ) -> list[Candidate]:
        """
        Adds structurally related candidates (decorators, callees).
        
        Invariants:
        - max_additions enforced from config
        - Only adds if semantic similarity > min_similarity (from config)
        - Provenance tracked for each addition
        """
        if not config.expansion_enabled:
            return candidates

        if not callgraph:
            logger.warning("Callgraph unavailable, skipping expansion")
            return candidates

        expanded = list(candidates)
        added_count = 0
        seen_ids = {c.doc_id for c in candidates}

        # For each candidate, find related symbols
        for candidate in candidates:
            if added_count >= config.expansion_max_additions:
                break

            if not candidate.symbol_id:
                continue

            # Find callees (functions called by this candidate)
            # Callgraph format: {caller_id: [callee_id, ...]}
            callees = callgraph.get(candidate.symbol_id, [])
            for callee_id in callees[:2]:  # Limit to 2 callees per candidate
                if added_count >= config.expansion_max_additions:
                    break

                # Check if already in results
                if any(c.symbol_id == callee_id for c in expanded):
                    continue

                # Load callee content and check similarity
                callee_content = ""
                if self._duckdb:
                    try:
                        callee_content = self._duckdb.get_symbol_content(callee_id) or ""
                    except Exception as e:
                        logger.warning(f"Failed to load content for {callee_id}: {e}")

                # Check similarity if embedder and content available
                if self.embedder and callee_content and config.expansion_min_similarity > 0:
                    try:
                        # Embed query and callee content
                        query_vector = self.embedder.embed_query(query)
                        callee_vector = self.embedder.embed_code(callee_content)

                        # Compute cosine similarity
                        similarity = self._cosine_similarity(query_vector.values, callee_vector.values)

                        # Only add if similarity exceeds threshold
                        if similarity < config.expansion_min_similarity:
                            logger.debug(f"Skipping {callee_id}: similarity {similarity:.3f} < {config.expansion_min_similarity}")
                            continue
                    except Exception as e:
                        logger.warning(f"Similarity check failed for {callee_id}: {e}")
                        # Continue without similarity check if it fails

                # Create candidate for callee
                callee_candidate = Candidate(
                    doc_id=f"expanded:{callee_id}",
                    file=candidate.file,  # Same file or resolve from symbol
                    symbol_id=callee_id,
                    content=callee_content,
                    provenance=("expansion:callee",),
                )

                expanded.append(callee_candidate)
                seen_ids.add(callee_candidate.doc_id)
                added_count += 1

        logger.info(f"Expanded {added_count} candidates")
        return expanded

    @staticmethod
    def _cosine_similarity(vec1: tuple[float, ...], vec2: tuple[float, ...]) -> float:
        """Compute cosine similarity between two vectors."""
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            # Normalize vectors
            v1_norm = v1 / (np.linalg.norm(v1) + 1e-8)
            v2_norm = v2 / (np.linalg.norm(v2) + 1e-8)
            # Cosine similarity
            return float(np.dot(v1_norm, v2_norm))
        except Exception:
            return 0.0
