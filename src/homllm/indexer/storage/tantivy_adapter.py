"""Tantivy adapter for BM25 lexical indexing."""

import logging
from pathlib import Path
from typing import Iterator

from homllm.common.types import Document
from homllm.indexer.interfaces import LexicalIndex

logger = logging.getLogger(__name__)

try:
    import tantivy
except ImportError:
    tantivy = None
    logger.warning("tantivy not available, BM25 indexing disabled")


class TantivyAdapter(LexicalIndex):
    """Tantivy-based BM25 index adapter."""

    def __init__(self, index_path: Path):
        """
        Initialize Tantivy index.
        
        Properties:
        - Deterministic indexing
        - Idempotent for same input
        """
        self.index_path = index_path
        self.index_path.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._schema = None
        self._writer = None

        if tantivy is None:
            logger.warning("Tantivy not available, using stub implementation")
            return

        self._init_index()

    def _init_index(self) -> None:
        """Initialize Tantivy index schema and index."""
        if tantivy is None:
            return

        try:
            # Define schema: doc_id (string), content (text)
            schema_builder = tantivy.SchemaBuilder()
            schema_builder.add_text_field("doc_id", stored=True)
            schema_builder.add_text_field("content", stored=False)
            self._schema = schema_builder.build()

            # Create or open index
            if (self.index_path / "meta.json").exists():
                # Open existing index
                self._index = tantivy.Index(self._schema, str(self.index_path))
            else:
                # Create new index
                self._index = tantivy.Index(self._schema, str(self.index_path))
        except Exception as e:
            logger.error(f"Failed to initialize Tantivy index: {e}")
            self._index = None

    def index(self, documents: Iterator[Document]) -> None:
        """
        Indexes documents. Idempotent for same input.
        
        Properties:
        - Deterministic for same input
        - No side effects beyond index updates
        """
        if tantivy is None or self._index is None:
            logger.warning("Tantivy not available, skipping indexing")
            return

        try:
            # Get writer
            writer = self._index.writer()

            # Index documents
            doc_count = 0
            for doc in documents:
                # Create Tantivy document - v0.25 API uses field names as strings
                tantivy_doc = tantivy.Document()
                tantivy_doc.add_text("doc_id", doc.doc_id)
                tantivy_doc.add_text("content", doc.content)

                writer.add_document(tantivy_doc)
                doc_count += 1

            # Commit changes
            writer.commit()
            logger.info(f"Indexed {doc_count} documents")

        except Exception as e:
            logger.error(f"Failed to index documents: {e}")

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """
        Returns ranked results as (doc_id, score) tuples.
        
        Properties:
        - Deterministic for same query
        - Results sorted by score descending
        """
        if tantivy is None or self._index is None:
            return []

        try:
            # Reload index to see latest changes
            self._index.reload()
            
            # Get searcher directly from index (v0.25.0 API)
            searcher = self._index.searcher()

            # Build query (search in content field)
            parsed_query = self._index.parse_query(query, ["content"])

            # Execute search
            search_result = searcher.search(parsed_query, top_k)

            # Extract results - SearchResult has .hits attribute
            results = []
            for (score, doc_address) in search_result.hits:
                retrieved_doc = searcher.doc(doc_address)
                # v0.25 API uses field name as string
                doc_id = retrieved_doc.get_first("doc_id")
                if doc_id:
                    results.append((doc_id, float(score)))

            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
