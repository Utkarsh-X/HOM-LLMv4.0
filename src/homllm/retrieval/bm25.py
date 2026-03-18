"""BM25 retrieval implementation."""

import logging
from pathlib import Path
from typing import Optional

from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.indexer.storage.tantivy_adapter import TantivyAdapter
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25-based lexical retrieval."""

    def __init__(self, index_path: Path, duckdb_path: Optional[Path] = None):
        """
        Initialize BM25 retriever.
        
        Properties:
        - Read-only access to index
        - Deterministic for same query
        
        Args:
            index_path: Path to Tantivy index
            duckdb_path: Path to DuckDB database (for content loading)
        """
        self.index_path = index_path
        self.duckdb_path = duckdb_path
        self._tantivy: Optional[TantivyAdapter] = None
        self._duckdb: Optional[DuckDBAdapter] = None
        self._init_index()

    def _init_index(self) -> None:
        """Initialize Tantivy index connection and DuckDB for content."""
        try:
            self._tantivy = TantivyAdapter(self.index_path)
        except Exception as e:
            logger.warning(f"Failed to initialize BM25 index: {e}")
            self._tantivy = None

        # Initialize DuckDB for content loading
        if self.duckdb_path:
            try:
                self._duckdb = DuckDBAdapter(self.duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for content: {e}")
                self._duckdb = None

    def supports_thread_safe_search(self) -> bool:
        """
        Whether this retriever can safely share adapter instances across threads.

        Conservative default is False unless explicitly proven thread-safe.
        """
        return False

    def clone_for_search(self) -> "BM25Retriever":
        """Create an isolated retriever instance for branch-local threaded search."""
        return BM25Retriever(self.index_path, duckdb_path=self.duckdb_path)

    def search(self, query: str, top_k: int) -> list[Candidate]:
        """
        Search using BM25.
        
        Returns:
            List of candidates sorted by BM25 score descending
        """
        if self._tantivy is None:
            logger.warning("BM25 index unavailable, returning empty results")
            return []

        try:
            # Search Tantivy index
            terms = [t for t in query.split() if t]
            results = self._tantivy.search(query, top_k)
            relaxed_used = False
            relaxed_term_count = 0
            if not results and query:
                relaxed_terms = terms[:12]
                if len(relaxed_terms) > 1:
                    relaxed_query = " OR ".join(relaxed_terms)
                    if relaxed_query and relaxed_query != query:
                        results = self._tantivy.search(relaxed_query, top_k)
                        relaxed_used = True
                        relaxed_term_count = len(relaxed_terms)
            self.last_search_meta = {
                "relaxed_used": relaxed_used,
                "relaxed_term_count": relaxed_term_count,
                "original_term_count": len(terms),
            }
            candidate_data_by_id: dict[str, Optional[dict]] = {}
            if self._duckdb and results:
                try:
                    candidate_data_by_id = self._duckdb.get_document_candidate_data_batch(
                        [doc_id for doc_id, _ in results]
                    )
                except Exception as e:
                    logger.warning(f"Failed to batch load BM25 metadata: {e}")
                    candidate_data_by_id = {}

            # Convert to candidates
            candidates = []
            for doc_id, score in results:
                file_path = ""
                symbol_id = None
                content = ""
                granularity_level = None

                if self._duckdb:
                    candidate_data = candidate_data_by_id.get(doc_id)
                    if candidate_data:
                        file_path = candidate_data.get("file", "")
                        symbol_id = candidate_data.get("symbol_id")
                        content = candidate_data.get("content", "")
                        granularity_level = candidate_data.get("granularity_level")
                        span_start = candidate_data.get("span_start")
                        span_end = candidate_data.get("span_end")
                        parent_symbol_id = candidate_data.get("parent_symbol_id")
                        entity_ids = tuple(candidate_data.get("entity_ids") or ())
                        doc_type = candidate_data.get("doc_type")
                        symbol_name = candidate_data.get("symbol_name")
                    else:
                        span_start = None
                        span_end = None
                        parent_symbol_id = None
                        entity_ids = ()
                        doc_type = None
                        symbol_name = None
                elif ":" in doc_id:
                    symbol_id = doc_id.split(":", 1)[1]
                    file_path = doc_id.split(":", 1)[0]
                    span_start = None
                    span_end = None
                    parent_symbol_id = None
                    entity_ids = ()
                    doc_type = None
                    symbol_name = None

                candidate = Candidate(
                    doc_id=doc_id,
                    file=file_path,
                    symbol_id=symbol_id,
                    content=content,
                    bm25_score=float(score),
                    provenance=("bm25",),
                    granularity_level=granularity_level,
                    span_start=span_start,
                    span_end=span_end,
                    parent_symbol_id=parent_symbol_id,
                    entity_ids=entity_ids,
                    doc_type=doc_type,
                    symbol_name=symbol_name,
                )
                candidates.append(candidate)

            return candidates

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
