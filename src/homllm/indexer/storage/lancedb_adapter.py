"""LanceDB adapter for vector indexing."""

import logging
from pathlib import Path
from typing import Iterator, Optional

from homllm.common.types import Document, Vector
from homllm.indexer.interfaces import Embedder

logger = logging.getLogger(__name__)

try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None
    pa = None
    logger.warning("lancedb not available, vector indexing disabled")


class LanceDBAdapter:
    """LanceDB adapter for vector storage."""

    def __init__(self, db_path: Path, embedder: Embedder):
        """
        Initialize LanceDB connection.
        
        Properties:
        - Versioned vector files
        - Deterministic indexing
        """
        self.db_path = db_path
        self.embedder = embedder
        self.db: Optional[lancedb.DBConnection] = None
        self.table_name = "vectors"
        self._table = None

        if lancedb is None:
            logger.warning("LanceDB not available, using stub implementation")
            return

        self.connect()

    def connect(self) -> None:
        """Establish database connection."""
        if lancedb is None:
            return

        try:
            self.db_path.mkdir(parents=True, exist_ok=True)
            self.db = lancedb.connect(str(self.db_path))

            # Check if table exists
            if self.table_name in self.db.table_names():
                self._table = self.db.open_table(self.table_name)
            else:
                # Table will be created on first index
                self._table = None

        except Exception as e:
            logger.error(f"Failed to connect to LanceDB: {e}")
            self.db = None

    def index(self, documents: Iterator[Document]) -> None:
        """
        Index documents with embeddings.
        
        Properties:
        - Embeds code chunks using embedder.embed_code() (no instruction prefix)
        - Deterministic for same input
        """
        if lancedb is None or self.db is None:
            logger.warning("LanceDB not available, skipping vector indexing")
            return

        try:
            # Collect documents and embeddings
            data = []
            for doc in documents:
                # Embed code chunk (NO instruction prefix per architecture)
                vector = self.embedder.embed_code(doc.content)

                data.append({
                    "doc_id": doc.doc_id,
                    "vector": vector.values,
                    "content": doc.content,
                    "metadata": str(doc.metadata),  # Store as string for now
                })

            if not data:
                return

            # Create Arrow table
            if pa is None:
                logger.error("pyarrow not available")
                return

            # Convert to Arrow format
            vectors = [item["vector"] for item in data]
            doc_ids = [item["doc_id"] for item in data]
            contents = [item["content"] for item in data]
            metadatas = [item["metadata"] for item in data]

            # Create schema
            vector_dim = len(vectors[0]) if vectors else self.embedder.dimension
            schema = pa.schema([
                pa.field("doc_id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), vector_dim)),
                pa.field("content", pa.string()),
                pa.field("metadata", pa.string()),
            ])

            # Create table
            table = pa.Table.from_pylist(data, schema=schema)

            # Create or append to table
            if self._table is None:
                self._table = self.db.create_table(self.table_name, table)
            else:
                self._table.add(table)

            logger.info(f"Indexed {len(data)} vectors")

        except Exception as e:
            logger.error(f"Failed to index vectors: {e}")

    def search(self, query_vector: Vector, top_k: int) -> list[tuple[str, float, str]]:
        """
        Vector similarity search.
        
        Returns:
            List of (doc_id, similarity_score, content) tuples, sorted descending by score
        """
        if lancedb is None or self.db is None or self._table is None:
            return []

        try:
            # Perform vector search - convert tuple to list for LanceDB
            query_list = list(query_vector.values)
            results = (
                self._table.search(query_list)
                .limit(top_k)
                .to_pandas()
            )

            # Extract results
            output = []
            for _, row in results.iterrows():
                doc_id = row.get("doc_id", "")
                content = row.get("content", "")
                # LanceDB returns distance, convert to similarity (1 - normalized distance)
                distance = row.get("_distance", float("inf"))
                similarity = 1.0 / (1.0 + distance)  # Simple conversion
                output.append((doc_id, float(similarity), str(content)))

            # Sort by similarity descending
            output.sort(key=lambda x: x[1], reverse=True)
            return output

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def close(self) -> None:
        """Close database connection."""
        # LanceDB doesn't require explicit closing
        self._table = None
        self.db = None
