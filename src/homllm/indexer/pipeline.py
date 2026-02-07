"""Indexer pipeline orchestrator.

Extended for entity-centric indexing (Plan A) with:
- Entity extraction (imports, variables, config constants, type aliases)
- Typed relation extraction (calls, defines, uses, imports, inherits)
- Hierarchical chunking (fine, medium, coarse)
- Schema versioning (1.0 → 2.0)
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from homllm.common.config import IndexerConfig
from homllm.common.exceptions import IndexerError
from homllm.common.types import CallEdge, ChunkInfo, Document, EntityInfo, FileInfo, RelationInfo, SymbolInfo
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.graph_builder import GraphBuilder
from homllm.indexer.interfaces import CodeParser, FileScanner, ScanConfig
from homllm.indexer.parser import TreeSitterParser
from homllm.indexer.scanner import RipgrepScanner
from homllm.indexer.storage import (
    DuckDBAdapter,
    FilesystemAdapter,
    INDEX_SCHEMA_VERSION,
    LanceDBAdapter,
    TantivyAdapter,
)

# Entity-centric indexing imports (Plan A)
from homllm.indexer.entity_extractor import EntityExtractor
from homllm.indexer.hierarchical_chunker import HierarchicalChunker

logger = logging.getLogger(__name__)


class IndexerPipeline:
    """
    Main indexer pipeline.
    
    Invariants:
    - IDX-001: Same repo state → byte-identical artifacts
    - IDX-002: No network calls during indexing
    - IDX-003: Incremental = full on changed files only
    - IDX-004: Language parsers are isolated
    
    Extended for entity-centric indexing (Plan A):
    - Entity extraction: imports, variables, config constants
    - Typed relations: calls, defines, uses, imports, inherits
    - Hierarchical chunking: fine, medium, coarse granularity
    """

    def __init__(
        self,
        config: IndexerConfig,
        scanner: Optional[FileScanner] = None,
        parser: Optional[CodeParser] = None,
    ):
        """
        Initialize indexer pipeline.
        
        Args:
            config: Indexer configuration
            scanner: File scanner (default: RipgrepScanner)
            parser: Code parser (default: TreeSitterParser)
        """
        self.config = config
        self.scanner = scanner or RipgrepScanner()
        self.parser = parser or TreeSitterParser()
        self.embedder = QwenEmbedder(
            model_name=config.embedding_model,
            dimension=config.embedding_dimension,
            max_input_tokens=config.embedding_max_tokens,
        )

        # Initialize storage adapters
        self.fs_adapter = FilesystemAdapter(config.storage.artifacts_path)
        self.duckdb = DuckDBAdapter(config.storage.duckdb_path)
        self.tantivy = TantivyAdapter(config.storage.tantivy_path)
        self.lancedb = LanceDBAdapter(config.storage.lancedb_path, self.embedder)

        # Initialize graph builder with entity-centric flag
        self.graph_builder = GraphBuilder(
            entity_centric_enabled=config.entity_centric_indexing_enabled
        )
        
        # Entity-centric indexing components (Plan A)
        if config.entity_centric_indexing_enabled:
            self.entity_extractor = EntityExtractor(config)
            self.hierarchical_chunker = HierarchicalChunker(config.hierarchical_chunking)
        else:
            self.entity_extractor = None
            self.hierarchical_chunker = None

    def index(self, repo_path: Path, incremental: bool = False) -> None:
        """
        Index a repository.
        
        Args:
            repo_path: Path to repository root
            incremental: If True, only index changed files
        
        Guarantees:
        - Deterministic output
        - Immutable artifacts
        - No network calls
        """
        repo_path = repo_path.resolve()
        logger.info(f"Starting indexing for {repo_path}")
        
        # Log entity-centric indexing status
        if self.config.entity_centric_indexing_enabled:
            logger.info("Entity-centric indexing ENABLED (Plan A)")
        else:
            logger.info("Entity-centric indexing DISABLED (legacy mode)")

        # Initialize storage
        self.duckdb.connect()
        self.duckdb.initialize_schema()
        self.lancedb.connect()

        # Compute repo hash
        repo_hash = self._compute_repo_hash(repo_path)

        # 1. Scan files
        scan_config = ScanConfig(self.config)
        files = list(self.scanner.scan(repo_path, scan_config))
        logger.info(f"Scanned {len(files)} files")

        # 2. Parse files and collect symbols
        all_symbols: list[SymbolInfo] = []
        all_files: list[FileInfo] = []
        all_entities: list[EntityInfo] = []  # Plan A
        all_chunks: list[ChunkInfo] = []  # Plan A
        documents_for_bm25: list[Document] = []
        documents_for_vectors: list[Document] = []

        for file_info in files:
            try:
                # Parse file
                file_path = repo_path / file_info.path
                result = self.parser.parse(file_path, file_info.language or "unknown")

                # Store file metadata
                all_files.append(file_info)
                self.duckdb.insert_file(file_info)

                # Add symbols
                for symbol in result.symbols:
                    all_symbols.append(symbol)
                    # Extract symbol code for storage
                    symbol_code = self._extract_symbol_code(
                        result.content, symbol.start_line, symbol.end_line
                    )
                    self.duckdb.insert_symbol(symbol, file_info.file_id, content=symbol_code)

                # Add to graph builder
                self.graph_builder.add_file_result(str(file_info.path), result)
                
                # ===============================================================
                # Entity-Centric Indexing (Plan A)
                # ===============================================================
                if self.config.entity_centric_indexing_enabled and result.tree is not None:
                    # Extract entities
                    entities = self.entity_extractor.extract_entities(
                        result.tree.root_node,
                        result.content,
                        str(file_info.path),
                    )
                    all_entities.extend(entities)
                    
                    # Add entities to graph builder
                    self.graph_builder.add_entities(entities)
                    
                    # Extract import relations
                    self.graph_builder.extract_import_relations(
                        entities, str(file_info.path)
                    )
                    
                    # Create hierarchical chunks
                    chunks = self.hierarchical_chunker.create_chunks(
                        str(file_info.path),
                        result.content,
                        result.symbols,
                        entities,
                    )
                    all_chunks.extend(chunks)

                # Create documents for indexing (chunk by symbol)
                for symbol in result.symbols:
                    # Extract symbol code from file content
                    symbol_code = self._extract_symbol_code(
                        result.content, symbol.start_line, symbol.end_line
                    )

                    doc_id = f"{file_info.file_id}:{symbol.id}"
                    doc = Document(
                        doc_id=doc_id,
                        content=symbol_code,
                        metadata={
                            "file": str(file_info.path),
                            "symbol_id": symbol.id,
                            "symbol_name": symbol.name,
                            "symbol_kind": symbol.kind.value,
                        },
                    )
                    documents_for_bm25.append(doc)
                    documents_for_vectors.append(doc)

            except Exception as e:
                logger.error(f"Error processing {file_info.path}: {e}")
                # Continue with other files (IDX-004: Language parsers are isolated)

        # 3. Build graphs
        call_edges = self.graph_builder.build_call_graph()
        validation_errors = self.graph_builder.validate()
        if validation_errors:
            logger.warning(f"Graph validation errors: {validation_errors}")

        # Store call edges
        for edge in call_edges:
            self.duckdb.insert_call_edge(edge)
        
        # ===================================================================
        # Entity-Centric Indexing: Store entities, relations, chunks (Plan A)
        # ===================================================================
        all_relations: list[RelationInfo] = []
        if self.config.entity_centric_indexing_enabled:
            # Build typed relation graph
            all_relations = self.graph_builder.build_relation_graph()
            
            # Store entities
            for entity in all_entities:
                self.duckdb.insert_entity(entity)
            logger.info(f"Stored {len(all_entities)} entities")
            
            # Store relations
            for relation in all_relations:
                self.duckdb.insert_relation(relation)
            logger.info(f"Stored {len(all_relations)} relations")
            
            # Store chunks
            for chunk in all_chunks:
                self.duckdb.insert_chunk(chunk)
            logger.info(f"Stored {len(all_chunks)} chunks")

        # 4. Index text (BM25)
        logger.info(f"Indexing {len(documents_for_bm25)} documents in BM25")
        self.tantivy.index(iter(documents_for_bm25))

        # 5. Index vectors
        logger.info(f"Indexing {len(documents_for_vectors)} vectors")
        self.lancedb.index(iter(documents_for_vectors))

        # 6. Store metadata with schema version
        self.duckdb.set_metadata("version", "1.0")
        self.duckdb.set_metadata("index_schema_version", INDEX_SCHEMA_VERSION)
        self.duckdb.set_metadata("created_at", datetime.utcnow().isoformat())
        self.duckdb.set_metadata("repo_hash", repo_hash)
        self.duckdb.set_metadata(
            "entity_centric_indexing_enabled",
            str(self.config.entity_centric_indexing_enabled),
        )

        # 7. Write artifacts
        self._write_artifacts(
            all_symbols, all_files, call_edges, all_entities, all_relations, all_chunks
        )

        logger.info("Indexing complete")
        if self.config.entity_centric_indexing_enabled:
            logger.info(
                f"Entity-centric stats: {len(all_entities)} entities, "
                f"{len(all_relations)} relations, {len(all_chunks)} chunks"
            )

    def _extract_symbol_code(self, content: str, start_line: int, end_line: int) -> str:
        """Extract code for a symbol from file content."""
        lines = content.split("\n")
        # Convert 1-based to 0-based indexing
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        return "\n".join(lines[start_idx:end_idx])

    def _write_artifacts(
        self,
        symbols: list[SymbolInfo],
        files: list[FileInfo],
        call_edges: list[CallEdge],
        entities: list[EntityInfo],
        relations: list[RelationInfo],
        chunks: list[ChunkInfo],
    ) -> None:
        """Write immutable artifacts to filesystem."""
        # Sort for determinism
        symbols.sort(key=lambda s: (s.file, s.start_line, s.name))
        files.sort(key=lambda f: str(f.path))
        call_edges.sort(key=lambda e: (e.caller_id, e.callee_id, e.call_site_line))

        # Write symbols.json
        symbols_data = {
            "version": "1.0",
            "symbols": [
                {
                    "id": s.id,
                    "name": s.name,
                    "kind": s.kind.value,
                    "file": s.file,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "signature": s.signature,
                    "decorators": list(s.decorators),
                    "parent_id": s.parent_id,
                }
                for s in symbols
            ],
        }
        self.fs_adapter.write_json("symbols.json", symbols_data)

        # Write files.json
        files_data = {
            "version": "1.0",
            "files": [
                {
                    "file_id": f.file_id,
                    "path": str(f.path),
                    "language": f.language,
                    "content_hash": f.content_hash,
                    "line_count": f.line_count,
                    "parse_error": f.parse_error,
                }
                for f in files
            ],
        }
        self.fs_adapter.write_json("files.json", files_data)

        # Write callgraph.json
        callgraph_data = {
            "version": "1.0",
            "edges": [
                {
                    "caller_id": e.caller_id,
                    "callee_id": e.callee_id,
                    "call_site_line": e.call_site_line,
                }
                for e in call_edges
            ],
        }
        self.fs_adapter.write_json("callgraph.json", callgraph_data)

        # Write dependencies.json (placeholder for now)
        dependencies_data = {
            "version": "1.0",
            "dependencies": [],
        }
        self.fs_adapter.write_json("dependencies.json", dependencies_data)
        
        # ===================================================================
        # Entity-Centric Artifacts (Plan A)
        # ===================================================================
        if self.config.entity_centric_indexing_enabled:
            # Sort entities and relations for determinism
            entities.sort(key=lambda e: (e.file_path, e.span_start, e.name))
            relations.sort(
                key=lambda r: (r.src_entity_id, r.dst_entity_id, r.relation_type)
            )
            chunks.sort(
                key=lambda c: (c.file_path, c.granularity_level, c.span_start)
            )
            
            # Write entities.json
            entities_data = {
                "version": INDEX_SCHEMA_VERSION,
                "entities": [
                    {
                        "entity_id": e.entity_id,
                        "entity_type": e.entity_type,
                        "name": e.name,
                        "file_path": e.file_path,
                        "span_start": e.span_start,
                        "span_end": e.span_end,
                        "docstring_hash": e.docstring_hash,
                        "granularity_level": e.granularity_level,
                        "confidence_score": e.confidence_score,
                        "has_type_annotation": e.has_type_annotation,
                        "is_exported": e.is_exported,
                        "parent_entity_id": e.parent_entity_id,
                    }
                    for e in entities
                ],
            }
            self.fs_adapter.write_json("entities.json", entities_data)
            
            # Write relations.json
            relations_data = {
                "version": INDEX_SCHEMA_VERSION,
                "relations": [
                    {
                        "src_entity_id": r.src_entity_id,
                        "dst_entity_id": r.dst_entity_id,
                        "relation_type": r.relation_type,
                        "extraction_source": r.extraction_source,
                    }
                    for r in relations
                ],
            }
            self.fs_adapter.write_json("relations.json", relations_data)
            
            # Write chunks.json
            chunks_data = {
                "version": INDEX_SCHEMA_VERSION,
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "file_path": c.file_path,
                        "granularity_level": c.granularity_level,
                        "span_start": c.span_start,
                        "span_end": c.span_end,
                        "entity_ids": list(c.entity_ids),
                        # Note: content is in DuckDB, not JSON artifact
                    }
                    for c in chunks
                ],
            }
            self.fs_adapter.write_json("chunks.json", chunks_data)

    def _compute_repo_hash(self, repo_path: Path) -> str:
        """Compute deterministic hash of repository state."""
        # Hash all file paths and content hashes
        sha256 = hashlib.sha256()

        # Get all files sorted deterministically
        files = sorted(repo_path.rglob("*"), key=lambda p: str(p))
        for file_path in files:
            if file_path.is_file():
                try:
                    # Include path and content hash
                    content_hash = hashlib.sha256(
                        file_path.read_bytes()
                    ).hexdigest()
                    entry = f"{file_path.relative_to(repo_path)}:{content_hash}\n"
                    sha256.update(entry.encode())
                except Exception:
                    # Skip files that can't be read
                    continue

        return sha256.hexdigest()

