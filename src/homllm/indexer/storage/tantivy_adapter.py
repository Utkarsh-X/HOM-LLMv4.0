"""Tantivy adapter for BM25 lexical indexing."""

import gc
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

# Stale lock files left behind when a previous writer was not cleanly released
# (e.g. a crashed or interrupted indexing process). On Windows these can block
# or confuse the next writer, so they are removed before opening a fresh one.
_STALE_LOCK_FILES = (".tantivy-writer.lock", ".tantivy-meta.lock")

# Default in-memory writer heap. Larger than tantivy's default so large
# repositories auto-commit fewer, larger segments (each auto-commit is a
# chance for a Windows file-race to leave the index uncommitted).
_WRITER_HEAP_SIZE = 256 * 1024 * 1024


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

    def _drop_writer(self) -> None:
        """Release any held writer deterministically instead of waiting on GC.

        A writer that stays alive holds the index writer lock; on Windows this
        can make a subsequent writer open fail or leave the index in a
        half-committed state. Drop the Python reference, force a GC pass, and
        remove stale lock files so the next writer starts clean.
        """
        if self._writer is not None:
            try:
                del self._writer
            except Exception:
                pass
            self._writer = None
            gc.collect()
        for lock_name in _STALE_LOCK_FILES:
            lock_path = self.index_path / lock_name
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _open_writer(self):
        """Open a fresh index writer, releasing any previous writer first."""
        self._drop_writer()
        if self._index is None:
            raise RuntimeError("Tantivy index is not initialized")
        self._writer = self._index.writer(heap_size=_WRITER_HEAP_SIZE)
        return self._writer

    def _registered_doc_count(self) -> int:
        """Number of documents currently registered in the committed index."""
        if self._index is None:
            return 0
        try:
            self._index.reload()
            return int(self._index.searcher().num_docs)
        except Exception:
            return 0

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

        Raises:
            RuntimeError: if the commit persistently fails to register after a
                single retry. A swallowed commit failure silently produces an
                unsearchable index, so this is surfaced loudly instead.
        """
        if tantivy is None or self._index is None:
            logger.warning("Tantivy not available, skipping indexing")
            return

        document_list = list(documents)
        if not document_list:
            return
        expected_count = self._registered_doc_count() + len(document_list)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                writer = self._open_writer()
                for doc in document_list:
                    # Create Tantivy document - v0.25 API uses field names as strings
                    tantivy_doc = tantivy.Document()
                    tantivy_doc.add_text("doc_id", doc.doc_id)
                    tantivy_doc.add_text("content", doc.content)
                    writer.add_document(tantivy_doc)
                writer.commit()
                self._drop_writer()
                after_count = self._registered_doc_count()
                if after_count >= expected_count:
                    logger.info(
                        "Indexed %d documents (registered %d -> %d)",
                        len(document_list),
                        expected_count - len(document_list),
                        after_count,
                    )
                    return
                # Commit ran but did not register: the index is in a broken
                # half-committed state. Reset it and retry once with a fresh
                # writer; after the reset the expected count is just the new
                # documents.
                logger.warning(
                    "BM25 commit did not register documents (expected %d, got %d); "
                    "resetting and retrying",
                    expected_count,
                    after_count,
                )
                self.reset()
                expected_count = len(document_list)
            except Exception as e:
                last_error = e
                logger.warning(
                    "BM25 indexing attempt %d failed: %s",
                    attempt + 1,
                    e,
                )
                try:
                    self._drop_writer()
                except Exception:
                    pass
        raise RuntimeError(
            "BM25 index commit failed after retry"
            + (f": {last_error}" if last_error is not None else "")
        )

    def delete_documents(self, doc_ids: list[str]) -> None:
        """Delete a set of documents by doc_id."""
        if tantivy is None or self._index is None or not doc_ids:
            return

        try:
            writer = self._open_writer()
            for doc_id in doc_ids:
                writer.delete_documents("doc_id", doc_id)
            writer.commit()
            self._drop_writer()
            logger.info("Deleted %d BM25 documents", len(doc_ids))
        except Exception as e:
            self._drop_writer()
            logger.error(f"Failed to delete BM25 documents: {e}")

    def reset(self) -> None:
        """Clear all BM25 documents while keeping schema/index."""
        if tantivy is None or self._index is None:
            return

        try:
            writer = self._open_writer()
            writer.delete_all_documents()
            writer.commit()
            self._drop_writer()
            logger.info("Reset BM25 index")
        except Exception as e:
            self._drop_writer()
            logger.error(f"Failed to reset BM25 index: {e}")

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
