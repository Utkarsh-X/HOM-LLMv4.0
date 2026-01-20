"""Retrieval pipeline orchestrator."""

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Optional

from homllm.common.config import Config
from homllm.common.types import Intent
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.storage.filesystem_adapter import FilesystemAdapter
from homllm.retrieval.bm25 import BM25Retriever
from homllm.retrieval.expander import StructuralExpanderImpl
from homllm.retrieval.hybrid import RRFHybridMerger
from homllm.retrieval.interfaces import (
    RetrievalConfig,
    RetrievalResult,
    StructuralExpander,
)
from homllm.retrieval.precision_recovery import PrecisionRecovery
from homllm.retrieval.preparer import SimpleQueryPreparer
from homllm.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    Main retrieval pipeline.
    
    Flow: Query → Ingest → Intent Classify → Query Prep → [BM25 ∥ Vector] → Hybrid Merge → Expand → Precision Recovery → Output
    
    Invariants:
    - RET-001: Same query + same index → same candidates
    - RET-002: Never modifies index artifacts
    - RET-003: All thresholds in config, not code
    - RET-004: BM25 and vector search are parallelizable
    - RET-005: Expansion is capped and auditable
    """

    def __init__(
        self,
        config: RetrievalConfig,
        bm25_index_path: Path,
        vector_db_path: Path,
        duckdb_path: Optional[Path] = None,
        artifacts_path: Optional[Path] = None,
        embedder: Optional[QwenEmbedder] = None,
        preparer: Optional[object] = None,
        merger: Optional[object] = None,
        expander: Optional[StructuralExpander] = None,
    ):
        """
        Initialize retrieval pipeline.
        
        Args:
            config: Retrieval configuration
            bm25_index_path: Path to Tantivy BM25 index
            vector_db_path: Path to LanceDB vector database
            duckdb_path: Path to DuckDB database (for content loading)
            artifacts_path: Path to index artifacts (for callgraph loading)
            embedder: Embedder for vector search (default: QwenEmbedder)
            preparer: Query preparer (default: SimpleQueryPreparer)
            merger: Hybrid merger (default: RRFHybridMerger)
            expander: Structural expander (default: StructuralExpanderImpl)
        """
        self.config = config
        self.embedder = embedder or QwenEmbedder()
        self.preparer = preparer or SimpleQueryPreparer()
        self.merger = merger or RRFHybridMerger()
        self.expander = expander or StructuralExpanderImpl(self.embedder, duckdb_path=duckdb_path)
        self.artifacts_path = artifacts_path

        # Initialize retrievers
        self.bm25_retriever = BM25Retriever(bm25_index_path, duckdb_path=duckdb_path)
        self.vector_retriever = VectorRetriever(vector_db_path, self.embedder)
        
        # Initialize precision recovery
        self.precision_recovery = PrecisionRecovery(
            self.bm25_retriever, self.vector_retriever
        )

    def retrieve(
        self, query: str, intent: Intent = Intent.UNKNOWN, top_k: int = 50
    ) -> RetrievalResult:
        """
        Execute retrieval pipeline.
        
        Args:
            query: User query
            intent: Query intent (default: UNKNOWN)
            top_k: Maximum number of candidates to return
        
        Returns:
            RetrievalResult with candidates and metadata
        
        Guarantees:
        - Deterministic for same query + same index
        - Never modifies index artifacts
        - All thresholds from config
        """
        query_id = str(uuid.uuid4())

        try:
            # 1. Prepare query
            prepared = self.preparer.prepare(query, intent)

            # 2. Parallel search: BM25 and Vector
            bm25_results = []
            vector_results = []

            # BM25 search
            try:
                bm25_results = self.bm25_retriever.search(
                    " ".join(prepared.lexical_terms), self.config.bm25_top_k
                )
            except Exception as e:
                logger.error(f"BM25 search failed: {e}")
                # Continue with vector-only results (RET-004)

            # Vector search
            try:
                vector_results = self.vector_retriever.search(
                    prepared.dense_query, self.config.vector_top_k
                )
            except Exception as e:
                logger.error(f"Vector search failed: {e}")
                # Continue with BM25-only results (RET-004)

            # If both failed, return empty result
            if not bm25_results and not vector_results:
                logger.warning("Both BM25 and vector search failed")
                return RetrievalResult(
                    candidates=[],
                    query_id=query_id,
                    metadata={"error": "both_searches_failed"},
                )

            # 3. Hybrid merge
            merged = self.merger.merge(bm25_results, vector_results, self.config)

            # 4. Structural expansion
            if self.config.expansion_enabled:
                # Load callgraph from artifacts
                callgraph = self._load_callgraph()
                merged = self.expander.expand(merged, query, callgraph, self.config)

            # 5. Precision recovery (missing entity detection)
            merged = self.precision_recovery.recover(
                merged, query, self.config, max_additions=3
            )

            # 6. Limit to top_k
            final_candidates = merged[:top_k]

            return RetrievalResult(
                candidates=final_candidates,
                query_id=query_id,
                metadata={
                    "bm25_count": len(bm25_results),
                    "vector_count": len(vector_results),
                    "merged_count": len(merged),
                    "final_count": len(final_candidates),
                },
            )

        except Exception as e:
            logger.error(f"Retrieval pipeline failed: {e}")
            return RetrievalResult(
                candidates=[],
                query_id=query_id,
                metadata={"error": str(e)},
            )

    def _load_callgraph(self) -> dict:
        """Load callgraph from artifacts."""
        if not self.artifacts_path:
            logger.warning("Artifacts path not provided, returning empty callgraph")
            return {}

        try:
            fs_adapter = FilesystemAdapter(self.artifacts_path)
            if fs_adapter.exists("callgraph.json"):
                callgraph_data = fs_adapter.read_json("callgraph.json")
                # Convert to dict format expected by expander: {caller_id: [callee_id, ...]}
                callgraph = {}
                for edge in callgraph_data.get("edges", []):
                    caller_id = edge.get("caller_id")
                    callee_id = edge.get("callee_id")
                    if caller_id and callee_id:
                        if caller_id not in callgraph:
                            callgraph[caller_id] = []
                        callgraph[caller_id].append(callee_id)
                return callgraph
            else:
                logger.warning("callgraph.json not found in artifacts")
                return {}
        except Exception as e:
            logger.warning(f"Failed to load callgraph: {e}")
            return {}
