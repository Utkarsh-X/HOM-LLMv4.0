"""Diagnostic-driven Mechanical Fixer.

Plan C: Single-action, deterministic corrective actions based on P1-P4 diagnostics.

Hard Constraints:
- No LLM planning or synthesis
- No retry loops (single pass only)
- No online learning
- No ranking changes
- No retrieval re-execution (additive expansions only)
- Max one mechanical action per query
- Deterministic, config-gated, auditable, reversible
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact, ContextBlock
    from homllm.intelligence.interfaces import DiagnosticSnapshot

logger = logging.getLogger(__name__)


# =============================================================================
# ACTION TYPES
# =============================================================================

class FixAction(str, Enum):
    """Available mechanical fix actions."""
    
    GRAPH_STITCH_RETRY = "GRAPH_STITCH_RETRY"
    SYMBOL_BACKFILL = "SYMBOL_BACKFILL"
    SEMANTIC_DEDUP_FORCE = "SEMANTIC_DEDUP_FORCE"
    UTILIZATION_EXPAND = "UTILIZATION_EXPAND"
    NO_OP = "NO_OP"


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class FixerThresholds:
    """Thresholds that trigger mechanical actions."""
    
    orphan_pct_trigger: float = 60.0
    redundancy_cluster_pct_trigger: float = 25.0
    used_budget_pct_low: float = 40.0


@dataclass
class FixerCaps:
    """Maximum additions per action type."""
    
    graph_stitch_max: int = 6
    symbol_backfill_max: int = 4
    utilization_expand_max: int = 10


@dataclass
class FixerConfig:
    """Mechanical fixer configuration."""
    
    enabled: bool = True
    action_priority: list[str] = field(default_factory=lambda: [
        "GRAPH_STITCH_RETRY",
        "SYMBOL_BACKFILL",
        "SEMANTIC_DEDUP_FORCE",
        "UTILIZATION_EXPAND",
    ])
    thresholds: FixerThresholds = field(default_factory=FixerThresholds)
    caps: FixerCaps = field(default_factory=FixerCaps)


@dataclass
class ABRMConfig:
    """ABRM (Assumption-Bound Reasoning Mode) configuration."""
    
    enabled: bool = True
    disable_on_cold_start: bool = True


# =============================================================================
# FIX RESULT
# =============================================================================

@dataclass
class FixResult:
    """Result of a mechanical fix attempt.
    
    Invariants:
    - Exactly one action or NO_OP
    - Provenance tag always present
    - Delta describes what changed
    """
    
    action: FixAction
    trigger: str  # e.g., "orphan_pct=65%"
    delta: dict  # e.g., {"blocks_added": 4, "blocks_removed": 0}
    improved: bool  # Did L1 sufficiency improve?
    provenance_tag: str  # e.g., "mechanical_fix:GRAPH_STITCH_RETRY"
    
    @property
    def was_applied(self) -> bool:
        """Check if an action was actually applied."""
        return self.action != FixAction.NO_OP
    
    def format_priming_notice(self) -> str:
        """Format the provenance priming injection for generation prompt."""
        if not self.was_applied:
            return ""
        
        blocks_added = self.delta.get("blocks_added", 0)
        blocks_removed = self.delta.get("blocks_removed", 0)
        
        parts = []
        if blocks_added > 0:
            parts.append(f"+{blocks_added} blocks")
        if blocks_removed > 0:
            parts.append(f"-{blocks_removed} blocks")
        
        delta_str = ", ".join(parts) if parts else "no change"
        
        return (
            f"Diagnostics triggered mechanical fix: {self.action.value} ({delta_str}). "
            "Context enhanced structurally."
        )


# =============================================================================
# MECHANICAL FIXER
# =============================================================================

class MechanicalFixer:
    """
    Diagnostic-driven mechanical fixer.
    
    Evaluates diagnostics once, selects the highest-priority applicable action,
    and applies exactly one bounded corrective action.
    
    Invariants:
    - Deterministic: same input → same output
    - Single action per query
    - All thresholds from config
    - Additive only (no retrieval re-execution)
    - Provenance tracked for all additions
    """
    
    def __init__(
        self,
        config: FixerConfig,
        duckdb_path: Optional[Path] = None,
    ):
        """
        Initialize mechanical fixer.
        
        Args:
            config: Fixer configuration
            duckdb_path: Path to DuckDB for symbol lookup
        """
        self.config = config
        self.duckdb_path = duckdb_path
        self._duckdb = None
        
        if duckdb_path:
            try:
                from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
                self._duckdb = DuckDBAdapter(duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for fixer: {e}")
    
    def apply(
        self,
        context: "ContextArtifact",
        diagnostics: "DiagnosticSnapshot",
    ) -> tuple["ContextArtifact", FixResult]:
        """
        Apply a single mechanical fix based on diagnostics.
        
        Args:
            context: Current context artifact
            diagnostics: Diagnostic snapshot (P1-P4)
        
        Returns:
            Tuple of (possibly augmented context, fix result)
        
        Invariants:
        - Exactly one action or NO_OP
        - Never modifies input context (returns new)
        - Provenance tracked
        """
        if not self.config.enabled:
            return context, self._no_op_result("fixer_disabled")
        
        # Evaluate diagnostic conditions
        conditions = self._evaluate_conditions(context, diagnostics)
        
        if not conditions:
            logger.debug("No fix conditions triggered")
            return context, self._no_op_result("no_conditions_triggered")
        
        # Select highest-priority action
        action = self._select_action(conditions)
        
        if action is None:
            return context, self._no_op_result("no_applicable_action")
        
        # Apply the selected action
        logger.info(f"Applying mechanical fix: {action.value}")
        
        if action == FixAction.GRAPH_STITCH_RETRY:
            return self._apply_graph_stitch_retry(context, diagnostics, conditions)
        elif action == FixAction.SYMBOL_BACKFILL:
            return self._apply_symbol_backfill(context, diagnostics, conditions)
        elif action == FixAction.SEMANTIC_DEDUP_FORCE:
            return self._apply_semantic_dedup_force(context, diagnostics, conditions)
        elif action == FixAction.UTILIZATION_EXPAND:
            return self._apply_utilization_expand(context, diagnostics, conditions)
        else:
            return context, self._no_op_result("unknown_action")
    
    def _evaluate_conditions(
        self,
        context: "ContextArtifact",
        diagnostics: "DiagnosticSnapshot",
    ) -> dict[str, dict]:
        """
        Evaluate diagnostic conditions for each action.
        
        Returns:
            Dict mapping action name to condition info (empty if not triggered)
        """
        conditions: dict[str, dict] = {}
        thresholds = self.config.thresholds
        
        # Check L1 structural diagnostics
        l1 = diagnostics.level1
        l1_result = l1.result if l1.status == "available" else None
        
        if l1_result:
            # Check orphan percentage (triggers GRAPH_STITCH_RETRY)
            # Orphan = block with no structural connections
            orphan_pct = self._compute_orphan_pct(l1_result, diagnostics)
            if orphan_pct > thresholds.orphan_pct_trigger:
                conditions["GRAPH_STITCH_RETRY"] = {
                    "trigger": f"orphan_pct={orphan_pct:.1f}%",
                    "value": orphan_pct,
                }
            
            # Check redundancy cluster percentage (triggers SEMANTIC_DEDUP_FORCE)
            redundancy_pct = self._compute_redundancy_pct(l1_result, diagnostics)
            if redundancy_pct > thresholds.redundancy_cluster_pct_trigger:
                conditions["SEMANTIC_DEDUP_FORCE"] = {
                    "trigger": f"redundancy_cluster_pct={redundancy_pct:.1f}%",
                    "value": redundancy_pct,
                }
            
            # Check budget utilization (triggers UTILIZATION_EXPAND)
            used_budget_pct = l1_result.used_budget_pct
            if used_budget_pct < thresholds.used_budget_pct_low:
                conditions["UTILIZATION_EXPAND"] = {
                    "trigger": f"used_budget_pct={used_budget_pct:.1f}%",
                    "value": used_budget_pct,
                }
        
        # Check L2/L3 for missing definitions (triggers SYMBOL_BACKFILL)
        missing_symbols = self._find_missing_symbols(diagnostics)
        if missing_symbols:
            conditions["SYMBOL_BACKFILL"] = {
                "trigger": f"missing_definitions={len(missing_symbols)}",
                "value": missing_symbols,
            }
        
        return conditions
    
    def _select_action(self, conditions: dict[str, dict]) -> Optional[FixAction]:
        """
        Select the highest-priority action from triggered conditions.
        
        Uses config.action_priority to determine order.
        """
        for action_name in self.config.action_priority:
            if action_name in conditions:
                try:
                    return FixAction(action_name)
                except ValueError:
                    logger.warning(f"Unknown action in priority list: {action_name}")
                    continue
        return None
    
    def _no_op_result(self, reason: str) -> FixResult:
        """Create a NO_OP result."""
        return FixResult(
            action=FixAction.NO_OP,
            trigger=reason,
            delta={},
            improved=False,
            provenance_tag="",
        )
    
    # =========================================================================
    # CONDITION EVALUATION HELPERS
    # =========================================================================
    
    def _compute_orphan_pct(
        self,
        l1_result,
        diagnostics: "DiagnosticSnapshot",
    ) -> float:
        """Compute percentage of structurally orphaned blocks."""
        # Orphan = block with no callgraph/relation connections
        # For now, use a heuristic based on provenance
        total_blocks = l1_result.total_blocks
        if total_blocks == 0:
            return 0.0
        
        # Count blocks without structural provenance
        orphan_count = 0
        l1_blocks = diagnostics.level1.blocks
        for block in l1_blocks:
            # Check if block has structural connections
            has_structural = any(
                "expansion" in prov or "callgraph" in prov or "graph_stitch" in prov
                for prov in getattr(block, "provenance", ())
            )
            if not has_structural:
                orphan_count += 1
        
        return (orphan_count / total_blocks) * 100.0 if total_blocks > 0 else 0.0
    
    def _compute_redundancy_pct(
        self,
        l1_result,
        diagnostics: "DiagnosticSnapshot",
    ) -> float:
        """Compute percentage of blocks in redundancy clusters."""
        total_blocks = l1_result.total_blocks
        if total_blocks == 0:
            return 0.0
        
        redundant_blocks = l1_result.redundant_blocks
        return (len(redundant_blocks) / total_blocks) * 100.0
    
    def _find_missing_symbols(
        self,
        diagnostics: "DiagnosticSnapshot",
    ) -> list[str]:
        """Find symbols referenced but not defined in context."""
        missing = []
        
        # Check L2 for concept gaps
        l2 = diagnostics.level2
        if l2.status == "available" and l2.result:
            # Look for gaps in the relational diagnostic
            result = l2.result
            if hasattr(result, "concept_gaps"):
                missing.extend(result.concept_gaps)
        
        # Check L3 for missing explanations
        l3 = diagnostics.level3
        if l3.status == "available" and l3.result:
            result = l3.result
            if hasattr(result, "missing_anchors"):
                missing.extend(result.missing_anchors)
        
        return list(set(missing))[:10]  # Dedupe and limit
    
    # =========================================================================
    # ACTION IMPLEMENTATIONS
    # =========================================================================
    
    def _apply_graph_stitch_retry(
        self,
        context: "ContextArtifact",
        diagnostics: "DiagnosticSnapshot",
        conditions: dict,
    ) -> tuple["ContextArtifact", FixResult]:
        """
        Apply GRAPH_STITCH_RETRY action.
        
        BFS on relations table to add structurally related blocks.
        """
        cap = self.config.caps.graph_stitch_max
        trigger = conditions["GRAPH_STITCH_RETRY"]["trigger"]
        
        # Collect seed symbol IDs from current context
        seed_ids = set()
        for block in context.blocks:
            if block.symbol_id:
                seed_ids.add(block.symbol_id)
        
        if not seed_ids or not self._duckdb:
            return context, FixResult(
                action=FixAction.GRAPH_STITCH_RETRY,
                trigger=trigger,
                delta={"blocks_added": 0},
                improved=False,
                provenance_tag="mechanical_fix:GRAPH_STITCH_RETRY",
            )
        
        # BFS to find related entities
        new_blocks = self._bfs_expand_symbols(seed_ids, context.blocks, cap)
        
        if not new_blocks:
            return context, FixResult(
                action=FixAction.GRAPH_STITCH_RETRY,
                trigger=trigger,
                delta={"blocks_added": 0},
                improved=False,
                provenance_tag="mechanical_fix:GRAPH_STITCH_RETRY",
            )
        
        # Create augmented context
        augmented_context = self._augment_context(context, new_blocks)
        
        return augmented_context, FixResult(
            action=FixAction.GRAPH_STITCH_RETRY,
            trigger=trigger,
            delta={"blocks_added": len(new_blocks)},
            improved=len(new_blocks) > 0,
            provenance_tag="mechanical_fix:GRAPH_STITCH_RETRY",
        )
    
    def _apply_symbol_backfill(
        self,
        context: "ContextArtifact",
        diagnostics: "DiagnosticSnapshot",
        conditions: dict,
    ) -> tuple["ContextArtifact", FixResult]:
        """
        Apply SYMBOL_BACKFILL action.
        
        Exact lookup for missing symbol definitions.
        """
        cap = self.config.caps.symbol_backfill_max
        trigger = conditions["SYMBOL_BACKFILL"]["trigger"]
        missing_symbols = conditions["SYMBOL_BACKFILL"]["value"]
        
        if not missing_symbols or not self._duckdb:
            return context, FixResult(
                action=FixAction.SYMBOL_BACKFILL,
                trigger=trigger,
                delta={"blocks_added": 0},
                improved=False,
                provenance_tag="mechanical_fix:SYMBOL_BACKFILL",
            )
        
        # Lookup symbol definitions
        new_blocks = self._lookup_symbols(missing_symbols[:cap], context.blocks)
        
        if not new_blocks:
            return context, FixResult(
                action=FixAction.SYMBOL_BACKFILL,
                trigger=trigger,
                delta={"blocks_added": 0},
                improved=False,
                provenance_tag="mechanical_fix:SYMBOL_BACKFILL",
            )
        
        # Create augmented context
        augmented_context = self._augment_context(context, new_blocks)
        
        return augmented_context, FixResult(
            action=FixAction.SYMBOL_BACKFILL,
            trigger=trigger,
            delta={"blocks_added": len(new_blocks)},
            improved=len(new_blocks) > 0,
            provenance_tag="mechanical_fix:SYMBOL_BACKFILL",
        )
    
    def _apply_semantic_dedup_force(
        self,
        context: "ContextArtifact",
        diagnostics: "DiagnosticSnapshot",
        conditions: dict,
    ) -> tuple["ContextArtifact", FixResult]:
        """
        Apply SEMANTIC_DEDUP_FORCE action.
        
        Remove high-similarity redundant blocks.
        """
        trigger = conditions["SEMANTIC_DEDUP_FORCE"]["trigger"]
        
        l1_result = diagnostics.level1.result
        if not l1_result:
            return context, FixResult(
                action=FixAction.SEMANTIC_DEDUP_FORCE,
                trigger=trigger,
                delta={"blocks_removed": 0},
                improved=False,
                provenance_tag="mechanical_fix:SEMANTIC_DEDUP_FORCE",
            )
        
        # Get redundant block IDs
        redundant_ids = set()
        for redundant in l1_result.redundant_blocks:
            if isinstance(redundant, dict) and "block_id" in redundant:
                redundant_ids.add(redundant["block_id"])
        
        if not redundant_ids:
            return context, FixResult(
                action=FixAction.SEMANTIC_DEDUP_FORCE,
                trigger=trigger,
                delta={"blocks_removed": 0},
                improved=False,
                provenance_tag="mechanical_fix:SEMANTIC_DEDUP_FORCE",
            )
        
        # Filter out redundant blocks
        filtered_blocks = tuple(
            b for b in context.blocks
            if b.block_id not in redundant_ids
        )
        
        removed_count = len(context.blocks) - len(filtered_blocks)
        
        if removed_count == 0:
            return context, FixResult(
                action=FixAction.SEMANTIC_DEDUP_FORCE,
                trigger=trigger,
                delta={"blocks_removed": 0},
                improved=False,
                provenance_tag="mechanical_fix:SEMANTIC_DEDUP_FORCE",
            )
        
        # Create reduced context
        from homllm.context.interfaces import ContextArtifact
        
        # Rebuild context text
        new_text = "\n\n".join(b.content for b in filtered_blocks)
        
        reduced_context = ContextArtifact(
            query_id=context.query_id,
            context_text=new_text,
            blocks=filtered_blocks,
            token_budget=context.token_budget,
            used_tokens=context.used_tokens - removed_count * 50,  # Rough estimate
            provenance={
                **context.provenance,
                "mechanical_fix": "SEMANTIC_DEDUP_FORCE",
            },
            explain_trace=context.explain_trace + (f"mechanical_fix:SEMANTIC_DEDUP_FORCE:-{removed_count}",),
        )
        
        return reduced_context, FixResult(
            action=FixAction.SEMANTIC_DEDUP_FORCE,
            trigger=trigger,
            delta={"blocks_removed": removed_count},
            improved=removed_count > 0,
            provenance_tag="mechanical_fix:SEMANTIC_DEDUP_FORCE",
        )
    
    def _apply_utilization_expand(
        self,
        context: "ContextArtifact",
        diagnostics: "DiagnosticSnapshot",
        conditions: dict,
    ) -> tuple["ContextArtifact", FixResult]:
        """
        Apply UTILIZATION_EXPAND action.
        
        Add next-tier blocks to fill unused budget.
        """
        cap = self.config.caps.utilization_expand_max
        trigger = conditions["UTILIZATION_EXPAND"]["trigger"]
        
        # Get existing block IDs
        existing_ids = {b.block_id for b in context.blocks}
        existing_symbols = {b.symbol_id for b in context.blocks if b.symbol_id}
        
        if not self._duckdb:
            return context, FixResult(
                action=FixAction.UTILIZATION_EXPAND,
                trigger=trigger,
                delta={"blocks_added": 0},
                improved=False,
                provenance_tag="mechanical_fix:UTILIZATION_EXPAND",
            )
        
        # Get next-tier blocks (symbols not in context)
        new_blocks = self._get_next_tier_blocks(existing_symbols, cap)
        
        if not new_blocks:
            return context, FixResult(
                action=FixAction.UTILIZATION_EXPAND,
                trigger=trigger,
                delta={"blocks_added": 0},
                improved=False,
                provenance_tag="mechanical_fix:UTILIZATION_EXPAND",
            )
        
        # Create augmented context
        augmented_context = self._augment_context(context, new_blocks)
        
        return augmented_context, FixResult(
            action=FixAction.UTILIZATION_EXPAND,
            trigger=trigger,
            delta={"blocks_added": len(new_blocks)},
            improved=len(new_blocks) > 0,
            provenance_tag="mechanical_fix:UTILIZATION_EXPAND",
        )
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _bfs_expand_symbols(
        self,
        seed_ids: set[str],
        existing_blocks: tuple,
        cap: int,
    ) -> list["ContextBlock"]:
        """BFS on relations to find related symbols."""
        if not self._duckdb or not self._duckdb.conn:
            return []
        
        existing_symbols = {b.symbol_id for b in existing_blocks if b.symbol_id}
        new_symbols = []
        visited = set(seed_ids)
        
        try:
            # Single-hop BFS
            for seed in seed_ids:
                if len(new_symbols) >= cap:
                    break
                
                result = self._duckdb.conn.execute(
                    """
                    SELECT dst_entity_id, relation_type
                    FROM relations
                    WHERE src_entity_id = ?
                    LIMIT 10
                    """,
                    [seed],
                ).fetchall()
                
                for row in result:
                    dst_id = row[0]
                    if dst_id not in visited and dst_id not in existing_symbols:
                        new_symbols.append(dst_id)
                        visited.add(dst_id)
                        if len(new_symbols) >= cap:
                            break
        except Exception as e:
            logger.warning(f"BFS expansion failed: {e}")
            return []
        
        # Convert symbol IDs to ContextBlocks
        return self._symbols_to_blocks(new_symbols, "mechanical_fix:GRAPH_STITCH_RETRY")
    
    def _lookup_symbols(
        self,
        symbol_names: list[str],
        existing_blocks: tuple,
    ) -> list["ContextBlock"]:
        """Lookup symbol definitions by name."""
        if not self._duckdb or not self._duckdb.conn:
            return []
        
        existing_symbols = {b.symbol_id for b in existing_blocks if b.symbol_id}
        found_symbols = []
        
        for name in symbol_names:
            try:
                result = self._duckdb.conn.execute(
                    """
                    SELECT entity_id, name, file_path
                    FROM entities
                    WHERE name = ? OR name LIKE ?
                    LIMIT 1
                    """,
                    [name, f"%{name}%"],
                ).fetchone()
                
                if result and result[0] not in existing_symbols:
                    found_symbols.append(result[0])
            except Exception as e:
                logger.debug(f"Symbol lookup failed for {name}: {e}")
        
        return self._symbols_to_blocks(found_symbols, "mechanical_fix:SYMBOL_BACKFILL")
    
    def _get_next_tier_blocks(
        self,
        existing_symbols: set[str],
        cap: int,
    ) -> list["ContextBlock"]:
        """Get next-tier blocks for utilization expansion."""
        if not self._duckdb or not self._duckdb.conn:
            return []
        
        try:
            # Get high-confidence entities not in context
            result = self._duckdb.conn.execute(
                """
                SELECT entity_id, name, file_path
                FROM entities
                WHERE confidence_score >= 0.7
                ORDER BY confidence_score DESC
                LIMIT ?
                """,
                [cap * 2],  # Fetch extra to filter
            ).fetchall()
            
            new_symbols = []
            for row in result:
                if row[0] not in existing_symbols and len(new_symbols) < cap:
                    new_symbols.append(row[0])
            
            return self._symbols_to_blocks(new_symbols, "mechanical_fix:UTILIZATION_EXPAND")
        except Exception as e:
            logger.warning(f"Utilization expansion failed: {e}")
            return []
    
    def _symbols_to_blocks(
        self,
        symbol_ids: list[str],
        provenance_tag: str,
    ) -> list["ContextBlock"]:
        """Convert symbol IDs to ContextBlock objects."""
        from homllm.context.interfaces import ContextBlock
        
        blocks = []
        
        for symbol_id in symbol_ids:
            try:
                content = self._duckdb.get_symbol_content(symbol_id) if self._duckdb else ""
                if not content:
                    continue
                
                # Get symbol metadata
                metadata = self._get_symbol_metadata(symbol_id)
                
                block = ContextBlock(
                    block_id=f"mech_fix:{symbol_id}",
                    file=metadata.get("file_path", ""),
                    start_line=metadata.get("span_start", 0),
                    end_line=metadata.get("span_end", 0),
                    content=content,
                    symbol_id=symbol_id,
                    symbol_name=metadata.get("name", ""),
                    provenance=(provenance_tag,),
                )
                blocks.append(block)
            except Exception as e:
                logger.debug(f"Failed to create block for {symbol_id}: {e}")
        
        return blocks
    
    def _get_symbol_metadata(self, symbol_id: str) -> dict:
        """Get symbol metadata from entities table."""
        if not self._duckdb or not self._duckdb.conn:
            return {}
        
        try:
            result = self._duckdb.conn.execute(
                """
                SELECT name, file_path, span_start, span_end
                FROM entities
                WHERE entity_id = ?
                """,
                [symbol_id],
            ).fetchone()
            
            if result:
                return {
                    "name": result[0],
                    "file_path": result[1],
                    "span_start": result[2],
                    "span_end": result[3],
                }
        except Exception:
            pass
        
        return {}
    
    def _augment_context(
        self,
        context: "ContextArtifact",
        new_blocks: list,
    ) -> "ContextArtifact":
        """Create augmented context with new blocks."""
        from homllm.context.interfaces import ContextArtifact
        
        augmented_blocks = context.blocks + tuple(new_blocks)
        
        # Rebuild context text
        new_text = context.context_text + "\n\n" + "\n\n".join(b.content for b in new_blocks)
        
        return ContextArtifact(
            query_id=context.query_id,
            context_text=new_text,
            blocks=augmented_blocks,
            token_budget=context.token_budget,
            used_tokens=context.used_tokens + sum(len(b.content) // 4 for b in new_blocks),
            provenance={
                **context.provenance,
                "mechanical_fix_blocks_added": len(new_blocks),
            },
            explain_trace=context.explain_trace + tuple(b.provenance[0] for b in new_blocks if b.provenance),
        )


# =============================================================================
# ABRM ACTIVATION LOGIC
# =============================================================================

def should_activate_abrm(
    diagnostics: "DiagnosticSnapshot",
    fix_result: Optional[FixResult],
    config: ABRMConfig,
    context: "ContextArtifact",
) -> bool:
    """
    Determine if ABRM should be activated.
    
    Trigger ABRM if ANY of:
    - P1 verdict ≠ SUFFICIENT
    - P2 remediation suggested (gap count > 0)
    - Mechanical fixer applied AND improved
    
    Disable if:
    - config.disable_on_cold_start and no blocks
    """
    if not config.enabled:
        return False
    
    # Cold start gate
    if config.disable_on_cold_start and len(context.blocks) == 0:
        logger.debug("ABRM disabled: cold start (no blocks)")
        return False
    
    # Check P1 verdict
    l1 = diagnostics.level1
    if l1.status == "available" and l1.result:
        # Check if result has a "sufficient" status
        used_pct = l1.result.used_budget_pct
        if used_pct < 40:  # Low utilization = not sufficient
            logger.debug(f"ABRM activated: P1 utilization low ({used_pct:.1f}%)")
            return True
    
    # Check P2 for remediation suggestions
    l2 = diagnostics.level2
    if l2.status == "available" and l2.result:
        result = l2.result
        if hasattr(result, "concept_gaps") and result.concept_gaps:
            logger.debug(f"ABRM activated: P2 concept gaps ({len(result.concept_gaps)})")
            return True
    
    # Check if mechanical fixer improved
    if fix_result and fix_result.was_applied and fix_result.improved:
        logger.debug(f"ABRM activated: mechanical fix improved ({fix_result.action.value})")
        return True
    
    return False


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "FixAction",
    "FixerConfig",
    "FixerThresholds",
    "FixerCaps",
    "ABRMConfig",
    "FixResult",
    "MechanicalFixer",
    "should_activate_abrm",
]
