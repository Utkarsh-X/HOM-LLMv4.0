"""Graph-based structural expansion (GRAPH_STITCH).

Part of Plan B: Retrieval Layer Activation.

BFS traversal on relations table to add structurally related entities.
Respects confidence threshold, depth limit, and relation priority.
"""

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


# Relation priority order (higher = more important)
DEFAULT_RELATION_PRIORITY: list[str] = [
    "calls",
    "overrides",
    "imports",
    "uses",
    "inherits",
    "type_annotates",
]


@dataclass
class GraphStitchConfig:
    """Configuration for graph stitch expansion."""
    
    enabled: bool = True
    max_depth: int = 2
    max_additions: int = 8
    min_confidence: float = 0.5
    relation_priority: list[str] = None
    
    def __post_init__(self):
        if self.relation_priority is None:
            self.relation_priority = DEFAULT_RELATION_PRIORITY.copy()


@dataclass(frozen=True)
class RelationEdge:
    """A relation edge in the graph."""
    
    src_entity_id: str
    dst_entity_id: str
    relation_type: str
    hop: int  # BFS hop count


class GraphStitchExpander:
    """
    Graph-based structural expansion using relations table.
    
    Performs BFS on the relation graph to find structurally related entities
    not already in the candidate set.
    
    Invariants:
        - Deterministic: same input → same output
        - Respects max_depth and max_additions limits
        - Only expands entities with confidence >= min_confidence
        - Provenance tracked: graph_stitch:{relation_type}:hop{n}
    """
    
    def __init__(
        self,
        duckdb_path: Optional[Path] = None,
        config: Optional[GraphStitchConfig] = None,
    ):
        """
        Initialize graph stitch expander.
        
        Args:
            duckdb_path: Path to DuckDB database
            config: Graph stitch configuration
        """
        self.config = config or GraphStitchConfig()
        self._duckdb: Optional[DuckDBAdapter] = None
        self.duckdb_path = duckdb_path
        
        if duckdb_path:
            try:
                self._duckdb = DuckDBAdapter(duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for graph stitch: {e}")
    
    def expand(
        self,
        candidates: list[Candidate],
        query: str,
    ) -> list[Candidate]:
        """
        Expand candidates using graph relation traversal.
        
        Args:
            candidates: Current candidate list
            query: Original query (for context, not used in expansion)
        
        Returns:
            Expanded candidate list with structurally related entities
        """
        if not self.config.enabled:
            return candidates
        
        if not self._duckdb:
            logger.debug("Graph stitch: DuckDB not available, skipping")
            return candidates
        
        # Get candidate symbol IDs as seed set
        seed_ids = {c.symbol_id for c in candidates if c.symbol_id}
        
        if not seed_ids:
            logger.debug("Graph stitch: No symbol IDs in candidates, skipping")
            return candidates
        
        # BFS to find related entities
        related = self._bfs_expand(seed_ids)
        
        if not related:
            return candidates
        
        # Convert to candidates
        expanded = list(candidates)
        seen_ids = {c.doc_id for c in candidates}
        additions = 0
        
        # Sort related by priority (relation type) then hop count
        priority_order = {r: i for i, r in enumerate(self.config.relation_priority)}
        related.sort(
            key=lambda e: (
                priority_order.get(e.relation_type, 999),
                e.hop,
            )
        )
        
        for edge in related:
            if additions >= self.config.max_additions:
                break
            
            entity_id = edge.dst_entity_id
            doc_id = f"graph_stitch:{entity_id}"
            
            if doc_id in seen_ids:
                continue
            
            # Load entity content
            entity_info = self._get_entity_info(entity_id)
            if not entity_info:
                continue
            
            # Check confidence threshold
            confidence = entity_info.get("confidence_score", 0.0)
            if confidence < self.config.min_confidence:
                logger.debug(
                    f"Graph stitch: Skipping {entity_id} "
                    f"(confidence {confidence:.2f} < {self.config.min_confidence})"
                )
                continue
            
            # Load content
            content = self._get_entity_content(entity_id, entity_info)
            
            # Create candidate with provenance
            provenance_tag = f"graph_stitch:{edge.relation_type}:hop{edge.hop}"
            
            candidate = Candidate(
                doc_id=doc_id,
                file=entity_info.get("file_path", ""),
                symbol_id=entity_id,
                content=content,
                provenance=(provenance_tag,),
            )
            
            expanded.append(candidate)
            seen_ids.add(doc_id)
            additions += 1
            
            logger.debug(
                f"Graph stitch: Added {entity_id} via {edge.relation_type} "
                f"(hop {edge.hop}, confidence {confidence:.2f})"
            )
        
        if additions > 0:
            logger.info(f"Graph stitch: Added {additions} related entities")
        
        return expanded
    
    def _bfs_expand(self, seed_ids: set[str]) -> list[RelationEdge]:
        """
        Perform BFS on relation graph starting from seed IDs.
        
        Args:
            seed_ids: Set of entity IDs to start from
        
        Returns:
            List of relation edges found (up to max_depth)
        """
        found: list[RelationEdge] = []
        visited: set[str] = set(seed_ids)
        queue: deque[tuple[str, int]] = deque()
        
        # Initialize queue with seed IDs at hop 0
        for seed in seed_ids:
            queue.append((seed, 0))
        
        while queue:
            entity_id, hop = queue.popleft()
            
            if hop >= self.config.max_depth:
                continue
            
            # Get outgoing relations
            relations = self._get_relations_from(entity_id)
            
            for rel in relations:
                dst = rel["dst_entity_id"]
                rel_type = rel["relation_type"]
                
                if dst in visited:
                    continue
                
                # Add edge
                edge = RelationEdge(
                    src_entity_id=entity_id,
                    dst_entity_id=dst,
                    relation_type=rel_type,
                    hop=hop + 1,
                )
                found.append(edge)
                
                # Mark visited and add to queue for next hop
                visited.add(dst)
                queue.append((dst, hop + 1))
        
        return found
    
    def _get_relations_from(self, entity_id: str) -> list[dict]:
        """Get relations where entity is the source."""
        if not self._duckdb or not self._duckdb.conn:
            return []
        
        try:
            result = self._duckdb.conn.execute(
                """
                SELECT dst_entity_id, relation_type
                FROM relations
                WHERE src_entity_id = ?
                """,
                [entity_id],
            ).fetchall()
            
            return [
                {"dst_entity_id": row[0], "relation_type": row[1]}
                for row in result
            ]
        except Exception as e:
            logger.debug(f"Failed to get relations for {entity_id}: {e}")
            return []
    
    def _get_entity_info(self, entity_id: str) -> Optional[dict]:
        """Get entity metadata."""
        if not self._duckdb or not self._duckdb.conn:
            return None
        
        try:
            result = self._duckdb.conn.execute(
                """
                SELECT entity_type, name, file_path, span_start, span_end,
                       confidence_score, granularity_level
                FROM entities
                WHERE entity_id = ?
                """,
                [entity_id],
            ).fetchone()
            
            if result:
                return {
                    "entity_type": result[0],
                    "name": result[1],
                    "file_path": result[2],
                    "span_start": result[3],
                    "span_end": result[4],
                    "confidence_score": result[5] or 0.0,
                    "granularity_level": result[6],
                }
            return None
        except Exception as e:
            logger.debug(f"Failed to get entity info for {entity_id}: {e}")
            return None
    
    def _get_entity_content(self, entity_id: str, entity_info: dict) -> str:
        """Get entity content from symbols table or chunks."""
        if not self._duckdb:
            return ""
        
        # Try symbols table first
        try:
            content = self._duckdb.get_symbol_content(entity_id)
            if content:
                return content
        except Exception:
            pass
        
        # Fallback: try chunks table
        try:
            if self._duckdb.conn:
                result = self._duckdb.conn.execute(
                    """
                    SELECT content
                    FROM chunks
                    WHERE chunk_id = ? OR ? = ANY(entity_ids)
                    LIMIT 1
                    """,
                    [entity_id, entity_id],
                ).fetchone()
                
                if result:
                    return result[0]
        except Exception:
            pass
        
        return ""
