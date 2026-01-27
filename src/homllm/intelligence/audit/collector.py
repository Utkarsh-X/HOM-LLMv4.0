"""
Assertion Suppression Audit Collector

Read-only collector that analyzes which assertions are suppressed
by intelligence actions without affecting execution.

CONSTRAINTS (ABSOLUTE):
- Does NOT modify any plans or actions
- Does NOT affect ContextModificationPlan execution
- Returns empty result when disabled
- Purely observational
- Deterministic: same input → same output
- No side effects
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from homllm.intelligence.audit.interfaces import (
    AssertionCandidate,
    SuppressionReason,
    AssertionAuditEntry,
    AuditResult,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.interfaces import DiagnosticSnapshot
    from homllm.intelligence.controller import ContextModificationPlan


# Action types that suppress/protect blocks
PROTECTIVE_ACTION_TYPES = frozenset({
    "PROTECT", "PRESERVE", "ANCHOR", "KEEP",
})

# Action types that remove/suppress blocks  
REMOVAL_ACTION_TYPES = frozenset({
    "DROP", "DEDUPE", "COMPACT",
})


class AuditCollector:
    """
    Read-only audit collector for assertion suppression analysis.
    
    This collector runs AFTER action engines produce their plans
    but BEFORE the plans are applied. It does NOT affect execution.
    
    Usage:
        collector = AuditCollector(enabled=True)
        result = collector.collect(snapshot, plan, context)
        
        # Result contains suppression analysis
        print(result.to_dict())
    
    Note:
        - When disabled, returns empty AuditResult
        - Never modifies inputs
        - Deterministic output
    """
    
    def __init__(self, enabled: bool = False):
        """
        Initialize the audit collector.
        
        Args:
            enabled: Whether to perform audit collection.
                     When False, collect() returns empty result.
        """
        self._enabled = enabled
    
    @property
    def enabled(self) -> bool:
        """Check if audit collection is enabled."""
        return self._enabled
    
    def collect(
        self,
        snapshot: "DiagnosticSnapshot",
        modification_plan: "ContextModificationPlan",
        context: "ContextArtifact",
    ) -> AuditResult:
        """
        Collect assertion suppression data.
        
        Analyzes the diagnostic snapshot and modification plan to identify
        which potential assertions are suppressed by protective actions.
        
        Args:
            snapshot: DiagnosticSnapshot from diagnostics engine
            modification_plan: ContextModificationPlan from intelligence controller
            context: Original ContextArtifact (read-only)
            
        Returns:
            AuditResult with suppression analysis.
            Empty result if collector is disabled.
            
        Note:
            - Does NOT modify any inputs
            - Does NOT affect plan execution
            - Purely observational
        """
        if not self._enabled:
            return AuditResult.empty()
        
        # Step 1: Extract assertion candidates from diagnostic blocks
        candidates = self._extract_assertion_candidates(snapshot, context)
        
        if not candidates:
            return AuditResult.empty()
        
        # Step 2: Build action map by block_id
        action_map = self._build_action_map(modification_plan)
        
        # Step 3: Analyze each assertion for suppression
        entries: list[AssertionAuditEntry] = []
        suppression_counts_by_level: dict[int, int] = {1: 0, 2: 0, 3: 0}
        
        for candidate in candidates:
            suppression_reasons = self._find_suppression_reasons(
                candidate, action_map
            )
            
            is_suppressed = len(suppression_reasons) > 0
            
            entries.append(AssertionAuditEntry(
                assertion=candidate,
                is_suppressed=is_suppressed,
                suppression_reasons=tuple(suppression_reasons),
            ))
            
            # Count suppressions by level
            if is_suppressed:
                for reason in suppression_reasons:
                    suppression_counts_by_level[reason.level] = (
                        suppression_counts_by_level.get(reason.level, 0) + 1
                    )
        
        # Step 4: Compute aggregates
        total = len(entries)
        suppressed = sum(1 for e in entries if e.is_suppressed)
        unblocked = total - suppressed
        
        breakdown = tuple(
            (level, count)
            for level, count in sorted(suppression_counts_by_level.items())
            if count > 0
        )
        
        return AuditResult(
            total_assertions_considered=total,
            assertions_suppressed=suppressed,
            assertions_unblocked=unblocked,
            suppression_breakdown_by_level=breakdown,
            entries=tuple(entries),
        )
    
    def _extract_assertion_candidates(
        self,
        snapshot: "DiagnosticSnapshot",
        context: "ContextArtifact",
    ) -> list[AssertionCandidate]:
        """
        Extract potential assertions from diagnostic blocks.
        
        Creates one assertion candidate per block based on its
        diagnostic characteristics. The assertion represents
        claims that could be made about the block's functionality.
        """
        candidates: list[AssertionCandidate] = []
        
        # Use Level-1 structural diagnostics for block info
        if snapshot.level1.status != "available":
            return candidates
        
        for block_diag in snapshot.level1.blocks:
            # Generate assertion based on block characteristics
            assertion_id = f"assertion_{block_diag.block_id}"
            
            # Create human-readable claim based on structural payload
            struct = block_diag.structural_payload
            textual_form = self._generate_claim_text(block_diag, struct)
            
            # Confidence based on signal ratio
            confidence = block_diag.signal_ratio
            
            candidates.append(AssertionCandidate(
                assertion_id=assertion_id,
                textual_form=textual_form,
                supporting_blocks=(block_diag.block_id,),
                confidence_signal=confidence,
            ))
        
        return candidates
    
    def _generate_claim_text(self, block_diag, struct) -> str:
        """Generate human-readable claim text for a block."""
        parts = []
        
        if struct.function_count > 0:
            parts.append(f"defines {struct.function_count} function(s)")
        if struct.class_count > 0:
            parts.append(f"defines {struct.class_count} class(es)")
        if struct.method_count > 0:
            parts.append(f"implements {struct.method_count} method(s)")
        
        if not parts:
            parts.append("contains code implementation")
        
        file_info = block_diag.file
        symbol_info = block_diag.symbol or "unnamed"
        
        return f"Block '{symbol_info}' in {file_info} {', '.join(parts)}"
    
    def _build_action_map(
        self,
        plan: "ContextModificationPlan",
    ) -> dict[str, list[tuple[int, str, str, str]]]:
        """
        Build a map of block_id -> list of (level, action_type, rule_name, justification).
        
        This allows quick lookup of actions targeting each block.
        """
        action_map: dict[str, list[tuple[int, str, str, str]]] = {}
        
        for action in plan.unified_actions:
            target = action.target
            if target not in action_map:
                action_map[target] = []
            
            # Extract rule name from original action if available
            rule_name = "unknown"
            orig = action.original_action
            if hasattr(orig, 'originating_rule'):
                rule_name = orig.originating_rule
            elif hasattr(orig, 'source_rule'):
                rule_name = orig.source_rule
            
            action_map[target].append((
                action.level,
                action.action_type,
                rule_name,
                action.justification,
            ))
        
        return action_map
    
    def _find_suppression_reasons(
        self,
        candidate: AssertionCandidate,
        action_map: dict[str, list[tuple[int, str, str, str]]],
    ) -> list[SuppressionReason]:
        """
        Find all suppression reasons for an assertion candidate.
        
        An assertion is considered suppressed if any of its supporting
        blocks have protective or removal actions applied.
        """
        reasons: list[SuppressionReason] = []
        
        for block_id in candidate.supporting_blocks:
            if block_id not in action_map:
                continue
            
            for level, action_type, rule_name, justification in action_map[block_id]:
                # Check if this action affects assertion visibility
                if action_type in PROTECTIVE_ACTION_TYPES:
                    explanation = (
                        f"Block protected by {action_type} action: {justification}"
                    )
                    reasons.append(SuppressionReason(
                        level=level,
                        rule_name=rule_name,
                        action_type=action_type,
                        blocking_block_id=block_id,
                        explanation=explanation,
                    ))
                elif action_type in REMOVAL_ACTION_TYPES:
                    explanation = (
                        f"Block removed/compacted by {action_type} action: {justification}"
                    )
                    reasons.append(SuppressionReason(
                        level=level,
                        rule_name=rule_name,
                        action_type=action_type,
                        blocking_block_id=block_id,
                        explanation=explanation,
                    ))
        
        return reasons


def create_audit_collector(enabled: bool = False) -> AuditCollector:
    """
    Factory function to create an AuditCollector.
    
    Args:
        enabled: Whether to enable audit collection
        
    Returns:
        Configured AuditCollector
    """
    return AuditCollector(enabled=enabled)


__all__ = [
    "AuditCollector",
    "create_audit_collector",
]
