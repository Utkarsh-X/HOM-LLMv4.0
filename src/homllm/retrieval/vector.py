"""Vector retrieval implementation."""

import logging
from pathlib import Path
from typing import Optional

from homllm.common.types import Vector
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.indexer.storage.lancedb_adapter import LanceDBAdapter
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


class VectorRetriever:
    """Vector-based semantic retrieval."""

    def __init__(
        self,
        db_path: Path,
        embedder: QwenEmbedder,
        duckdb_path: Optional[Path] = None,
        calibration_mode: str = "legacy",
    ):
        """
        Initialize vector retriever.
        
        Properties:
        - Read-only access to index
        - Deterministic for same query
        """
        self.db_path = db_path
        self.embedder = embedder
        self.duckdb_path = duckdb_path
        self.calibration_mode = str(calibration_mode).strip().lower()
        if self.calibration_mode not in {"legacy", "calibrated_v1"}:
            raise ValueError(
                "vector calibration_mode must be one of: legacy, calibrated_v1"
            )
        self._lancedb: Optional[LanceDBAdapter] = None
        self._duckdb: Optional[DuckDBAdapter] = None
        self._init_index()

    def _init_index(self) -> None:
        """Initialize LanceDB connection."""
        try:
            self._lancedb = LanceDBAdapter(self.db_path, self.embedder)
            self._lancedb.connect()
        except Exception as e:
            logger.warning(f"Failed to initialize vector index: {e}")
            self._lancedb = None
        if self.duckdb_path:
            try:
                self._duckdb = DuckDBAdapter(self.duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for vector metadata: {e}")
                self._duckdb = None

    def supports_thread_safe_search(self) -> bool:
        """
        Whether this retriever can safely share adapter instances across threads.

        Conservative default is False unless explicitly proven thread-safe.
        """
        return False

    def clone_for_search(self) -> "VectorRetriever":
        """Create an isolated retriever instance for branch-local threaded search."""
        return VectorRetriever(
            self.db_path,
            self.embedder,
            duckdb_path=self.duckdb_path,
            calibration_mode=self.calibration_mode,
        )

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
            results = self._lancedb.search(
                query_vector,
                top_k,
                calibration_mode=self.calibration_mode,
            )
            candidate_data_by_id: dict[str, Optional[dict]] = {}
            if self._duckdb and results:
                try:
                    candidate_data_by_id = self._duckdb.get_document_candidate_data_batch(
                        [doc_id for doc_id, _, _, _ in results]
                    )
                except Exception as e:
                    logger.warning(f"Failed to batch load vector metadata: {e}")
                    candidate_data_by_id = {}

            # Convert to candidates
            candidates = []
            for doc_id, score, content, metadata in results:
                file_path = metadata.get("file_path") or metadata.get("file") or ""
                symbol_id = metadata.get("symbol_id")
                granularity_level = metadata.get("granularity_level")
                span_start = None
                span_end = None
                parent_symbol_id = None
                entity_ids: tuple[str, ...] = ()
                doc_type = None

                if self._duckdb:
                    candidate_data = candidate_data_by_id.get(doc_id)
                    if candidate_data:
                        file_path = candidate_data.get("file", file_path)
                        symbol_id = candidate_data.get("symbol_id", symbol_id)
                        content = candidate_data.get("content") or content
                        granularity_level = candidate_data.get(
                            "granularity_level", granularity_level
                        )
                        span_start = candidate_data.get("span_start")
                        span_end = candidate_data.get("span_end")
                        parent_symbol_id = candidate_data.get("parent_symbol_id")
                        entity_ids = tuple(candidate_data.get("entity_ids") or ())
                        doc_type = candidate_data.get("doc_type")
                elif not symbol_id and ":" in doc_id:
                    symbol_id = doc_id.split(":", 1)[1]

                candidate = Candidate(
                    doc_id=doc_id,
                    file=file_path,
                    symbol_id=symbol_id,
                    content=content,  # Loaded from LanceDB
                    vector_score=float(score),
                    provenance=("vector",),
                    granularity_level=granularity_level,
                    span_start=span_start,
                    span_end=span_end,
                    parent_symbol_id=parent_symbol_id,
                    entity_ids=entity_ids,
                    doc_type=doc_type,
                )
                candidates.append(candidate)

            return candidates

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
