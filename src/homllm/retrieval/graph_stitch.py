"""Graph-based structural expansion (GRAPH_STITCH).

Part of Plan B: Retrieval Layer Activation.

BFS traversal on relations table to add structurally related entities.
Respects confidence threshold, depth limit, and relation priority.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


# Relation priority order (higher = more important)
DEFAULT_RELATION_PRIORITY: list[str] = [
    "resolves_to",
    "calls",
    "overrides",
    "uses",
    "imports",
    "inherits",
    "type_annotates",
]

HIGH_PRIORITY_RELATIONS: set[str] = {
    "DEFINES",
    "CALLS",
    "RESOLVES_TO",
    "INHERITS",
    "OVERRIDES",
}
LOW_PRIORITY_RELATIONS: set[str] = {"IMPORTS", "USES"}


@dataclass
class GraphStitchConfig:
    """Configuration for graph stitch expansion."""
    
    enabled: bool = True
    max_depth: int = 2
    max_additions: int = 8
    min_confidence: float = 0.5
    relation_priority: list[str] = None
    graph_cache_enabled: bool = True
    beam_high: int = 8
    beam_low: int = 3
    
    def __post_init__(self):
        if self.relation_priority is None:
            self.relation_priority = DEFAULT_RELATION_PRIORITY.copy()
        self.relation_priority = [str(r).lower() for r in self.relation_priority]


@dataclass(frozen=True)
class RelationEdge:
    """A relation edge in the graph."""
    
    src_entity_id: str
    dst_entity_id: str
    relation_type: str
    hop: int  # BFS hop count
    confidence: float = 0.0


class GraphTopology:
    """Singleton in-memory graph topology for relations table."""

    _instance: Optional["GraphTopology"] = None

    def __init__(self):
        self._loaded = False
        self._loaded_path: Optional[Path] = None
        self.adjacency: dict[str, list[tuple[str, str, float]]] = defaultdict(list)

    @classmethod
    def get_instance(cls, duckdb_path: Optional[Path]) -> Optional["GraphTopology"]:
        if duckdb_path is None:
            return None
        resolved_path = duckdb_path.resolve()
        if cls._instance is None:
            cls._instance = GraphTopology()
        if (not cls._instance._loaded) or (cls._instance._loaded_path != resolved_path):
            cls._instance._load(resolved_path)
        return cls._instance

    def _load(self, duckdb_path: Path) -> None:
        start = time.perf_counter()
        adapter = DuckDBAdapter(duckdb_path)
        self.adjacency = defaultdict(list)
        try:
            adapter.connect()
            try:
                rows = adapter.conn.execute(
                    """
                    SELECT src_entity_id, dst_entity_id, relation_type, confidence_score
                    FROM relations
                    ORDER BY src_entity_id ASC, relation_type ASC, dst_entity_id ASC
                    """
                ).fetchall()
                for src, dst, rel_type, conf in rows:
                    rel = str(rel_type).upper()
                    self.adjacency[str(src)].append((str(dst), rel, float(conf or 0.0)))
            except Exception:
                rows = adapter.conn.execute(
                    """
                    SELECT src_entity_id, dst_entity_id, relation_type
                    FROM relations
                    ORDER BY src_entity_id ASC, relation_type ASC, dst_entity_id ASC
                    """
                ).fetchall()
                for src, dst, rel_type in rows:
                    rel = str(rel_type).upper()
                    self.adjacency[str(src)].append((str(dst), rel, 1.0))
            self._loaded = True
            self._loaded_path = duckdb_path
            nodes = len(self.adjacency)
            edges = sum(len(v) for v in self.adjacency.values())
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "GraphTopology: Loaded cache nodes=%d edges=%d in %.1f ms",
                nodes,
                edges,
                elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"GraphTopology: Failed to load relations into memory: {e}")
        finally:
            try:
                if adapter.conn:
                    adapter.conn.close()
            except Exception:
                pass


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
        self._graph_topology: Optional[GraphTopology] = None
        self._cache_hits = 0
        self._cache_fallbacks = 0
        
        if duckdb_path:
            try:
                self._duckdb = DuckDBAdapter(duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for graph stitch: {e}")
        
        if self.config.graph_cache_enabled:
            self._graph_topology = GraphTopology.get_instance(duckdb_path)
    
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
        bfs_start = time.perf_counter()
        self._cache_hits = 0
        self._cache_fallbacks = 0
        hop_stats: dict[int, dict[str, int]] = defaultdict(
            lambda: {"high": 0, "low": 0, "total_before": 0, "after": 0}
        )
        related, visited_nodes, neighbors_before, neighbors_after = self._bfs_expand(
            seed_ids, hop_stats
        )
        bfs_ms = (time.perf_counter() - bfs_start) * 1000
        
        if not related:
            logger.info(
                "GraphStitch: query=\"%s\" cache_used=%s cache_hits=%d cache_fallbacks=%d bfs_ms=%.1f visited=%d neighbors_before=%d neighbors_after=%d additions=0",
                query[:80].replace("\n", " "),
                bool(self.config.graph_cache_enabled and self._graph_topology),
                self._cache_hits,
                self._cache_fallbacks,
                bfs_ms,
                visited_nodes,
                neighbors_before,
                neighbors_after,
            )
            return candidates
        
        # Convert to candidates
        expanded = list(candidates)
        seen_ids = {c.doc_id for c in candidates}
        additions = 0
        
        # Sort related by priority (relation type) then hop count
        priority_order = {
            str(relation).upper(): index
            for index, relation in enumerate(self.config.relation_priority)
        }
        related.sort(
            key=lambda e: (
                priority_order.get(e.relation_type, 999),
                e.hop,
                -float(e.confidence),
                e.relation_type,
                e.dst_entity_id,
                e.src_entity_id,
            )
        )
        
        entity_info_ms = 0.0
        content_ms = 0.0
        for edge in related:
            if additions >= self.config.max_additions:
                break
            
            entity_id = edge.dst_entity_id
            doc_id = f"graph_stitch:{entity_id}"
            
            if doc_id in seen_ids:
                continue
            
            # Load entity content
            info_start = time.perf_counter()
            entity_info = self._get_entity_info(entity_id)
            entity_info_ms += (time.perf_counter() - info_start) * 1000
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
            content_start = time.perf_counter()
            content = self._get_entity_content(entity_id, entity_info)
            content_ms += (time.perf_counter() - content_start) * 1000
            
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
        
        hop_entries = sorted(hop_stats.items())
        hop_count = len(hop_entries)
        avg_high = sum(v["high"] for _, v in hop_entries) / hop_count if hop_count else 0.0
        avg_low = sum(v["low"] for _, v in hop_entries) / hop_count if hop_count else 0.0
        avg_total = sum(v["total_before"] for _, v in hop_entries) / hop_count if hop_count else 0.0
        avg_after = sum(v["after"] for _, v in hop_entries) / hop_count if hop_count else 0.0
        
        logger.info(
            "GraphStitch: query=\"%s\" cache_used=%s cache_hits=%d cache_fallbacks=%d bfs_ms=%.1f entity_info_ms=%.1f content_ms=%.1f visited=%d neighbors_before=%d neighbors_after=%d avg_high=%.1f avg_low=%.1f avg_total=%.1f avg_after=%.1f additions=%d",
            query[:80].replace("\n", " "),
            bool(self.config.graph_cache_enabled and self._graph_topology),
            self._cache_hits,
            self._cache_fallbacks,
            bfs_ms,
            entity_info_ms,
            content_ms,
            visited_nodes,
            neighbors_before,
            neighbors_after,
            avg_high,
            avg_low,
            avg_total,
            avg_after,
            additions,
        )
        
        return expanded
    
    def _bfs_expand(
        self,
        seed_ids: set[str],
        hop_stats: dict[int, dict[str, int]],
    ) -> tuple[list[RelationEdge], int, int, int]:
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
        neighbors_before = 0
        neighbors_after = 0

        # Initialize queue with seed IDs at hop 0
        for seed in sorted(seed_ids):
            queue.append((seed, 0))
        
        while queue:
            entity_id, hop = queue.popleft()
            
            if hop >= self.config.max_depth:
                continue
            
            # Get outgoing relations
            relations = self._get_relations_from(entity_id)
            if not relations:
                continue

            high: list[dict] = []
            low: list[dict] = []
            for rel in relations:
                rel_type = rel["relation_type"]
                if rel_type in HIGH_PRIORITY_RELATIONS:
                    high.append(rel)
                else:
                    low.append(rel)
            
            high.sort(
                key=lambda r: (
                    -float(r.get("confidence", 0.0)),
                    str(r.get("relation_type", "")),
                    str(r.get("dst_entity_id", "")),
                )
            )
            low.sort(
                key=lambda r: (
                    -float(r.get("confidence", 0.0)),
                    str(r.get("relation_type", "")),
                    str(r.get("dst_entity_id", "")),
                )
            )
            
            high_before = len(high)
            low_before = len(low)
            neighbors_before += high_before + low_before
            high = high[: self.config.beam_high]
            low = low[: self.config.beam_low]
            pruned = high + low
            neighbors_after += len(pruned)
            
            hop_stats[hop]["high"] += len(high)
            hop_stats[hop]["low"] += len(low)
            hop_stats[hop]["total_before"] += high_before + low_before
            hop_stats[hop]["after"] += len(pruned)
            
            for rel in pruned:
                dst = rel["dst_entity_id"]
                rel_type = rel["relation_type"]
                conf = rel.get("confidence", 0.0)
                
                if dst in visited:
                    continue
                
                # Add edge
                edge = RelationEdge(
                    src_entity_id=entity_id,
                    dst_entity_id=dst,
                    relation_type=rel_type,
                    hop=hop + 1,
                    confidence=conf,
                )
                found.append(edge)
                
                # Mark visited and add to queue for next hop
                visited.add(dst)
                queue.append((dst, hop + 1))
        
        return found, len(visited), neighbors_before, neighbors_after
    
    def _get_relations_from(self, entity_id: str) -> list[dict]:
        """Get relations where entity is the source."""
        def _sort_key(row: dict) -> tuple[float, str, str]:
            return (
                -float(row.get("confidence", 0.0)),
                str(row.get("relation_type", "")),
                str(row.get("dst_entity_id", "")),
            )

        if self.config.graph_cache_enabled and self._graph_topology:
            self._cache_hits += 1
            items = self._graph_topology.adjacency.get(entity_id, [])
            rows = [
                {
                    "dst_entity_id": dst,
                    "relation_type": rel_type,
                    "confidence": conf,
                }
                for dst, rel_type, conf in items
            ]
            rows.sort(key=_sort_key)
            return rows
        if not self._duckdb or not self._duckdb.conn:
            return []
        
        self._cache_fallbacks += 1
        try:
            result = self._duckdb.conn.execute(
                """
                SELECT dst_entity_id, relation_type
                FROM relations
                WHERE src_entity_id = ?
                ORDER BY relation_type ASC, dst_entity_id ASC
                """,
                [entity_id],
            ).fetchall()
            
            rows = [
                {
                    "dst_entity_id": row[0],
                    "relation_type": str(row[1]).upper(),
                    "confidence": 1.0,
                }
                for row in result
            ]
            rows.sort(key=_sort_key)
            return rows
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
