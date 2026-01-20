"""Vector retrieval implementation."""

import logging
from pathlib import Path
from typing import Optional

from homllm.common.types import Vector
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.storage.lancedb_adapter import LanceDBAdapter
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Vector-based semantic retrieval."""

    def __init__(self, db_path: Path, embedder: QwenEmbedder):
        """
        Initialize vector retriever.
        
        Properties:
        - Read-only access to index
        - Deterministic for same query
        """
        self.db_path = db_path
        self.embedder = embedder
        self._lancedb: Optional[LanceDBAdapter] = None
        self._init_index()

    def _init_index(self) -> None:
        """Initialize LanceDB connection."""
        try:
            self._lancedb = LanceDBAdapter(self.db_path, self.embedder)
            self._lancedb.connect()
        except Exception as e:
            logger.warning(f"Failed to initialize vector index: {e}")
            self._lancedb = None

    def search(self, query: str, top_k: int) -> list[Candidate]:
        """
        Search using vector similarity.
        
        Returns:
            List of candidates sorted by vector score descending
        """
        if self._lancedb is None:
            logger.warning("Vector index unavailable, returning empty results")
            return []

        try:
            # Embed query (WITH instruction prefix)
            query_vector = self.embedder.embed_query(query)

            # Search vector index
            results = self._lancedb.search(query_vector, top_k)

            # Convert to candidates
            candidates = []
            for doc_id, score, content in results:
                # Parse doc_id
                parts = doc_id.split(":", 1)
                file_id = parts[0] if parts else ""
                symbol_id = parts[1] if len(parts) > 1 else None

                candidate = Candidate(
                    doc_id=doc_id,
                    file=file_id,
                    symbol_id=symbol_id,
                    content=content,  # Loaded from LanceDB
                    vector_score=float(score),
                    provenance=("vector",),
                )
                candidates.append(candidate)

            return candidates

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
