"""
Module 2: Explanatory Role Classification

Assigns semantic roles to each context block.

Roles:
- DEFINE: Introduces/defines a concept
- IMPLEMENT: Contains implementation logic
- USE: Uses/calls other components
- EXPLAIN: Contains explanatory content (docstrings, comments)
- SUPPORT: Supporting/utility code
- NOISE: Low-signal content (logging, boilerplate)

CONSTRAINTS:
- Deterministic signals only
- No ML/LLM
- Read-only
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from diagnostics.context.inspect_context import IntraBlockDiagnostic
from diagnostics.common.utils import safe_divide


class ExplanatoryRole(Enum):
    """Semantic role of a context block."""
    DEFINE = "DEFINE"       # Definition/declaration
    IMPLEMENT = "IMPLEMENT" # Implementation logic
    USE = "USE"            # Usage/invocation
    EXPLAIN = "EXPLAIN"    # Explanatory content
    SUPPORT = "SUPPORT"    # Support/utility
    NOISE = "NOISE"        # Low-signal noise


@dataclass
class BlockRole:
    """Role assignment for a block."""
    
    block_id: str
    primary_role: ExplanatoryRole
    secondary_role: Optional[ExplanatoryRole] = None
    confidence: float = 0.0
    
    # Role scores (for debugging)
    role_scores: dict[str, float] = field(default_factory=dict)
    
    # Reasons for classification
    reasons: list[str] = field(default_factory=list)


class ExplanatoryRoleAnalyzer:
    """
    Assigns semantic roles to context blocks.
    
    Uses deterministic signals:
    - Identifier introduction vs reuse
    - Docstring density
    - Control-flow dominance
    - Logging/error-handling ratio
    """
    
    def __init__(self):
        # Thresholds
        self.docstring_threshold = 20.0   # % for EXPLAIN
        self.logging_threshold = 15.0     # % for NOISE
        self.code_threshold = 40.0        # % for IMPLEMENT
        self.signature_threshold = 30.0   # % for DEFINE
    
    def analyze_block(self, block: IntraBlockDiagnostic) -> BlockRole:
        """
        Assign role to a single block.
        
        Args:
            block: Level-1 diagnostic for the block
            
        Returns:
            BlockRole with primary and secondary roles
        """
        scores = self._compute_role_scores(block)
        
        # Sort by score descending
        sorted_roles = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        primary = ExplanatoryRole[sorted_roles[0][0]]
        primary_score = sorted_roles[0][1]
        
        # Secondary role if close in score
        secondary = None
        if len(sorted_roles) > 1 and sorted_roles[1][1] > 0.3:
            secondary = ExplanatoryRole[sorted_roles[1][0]]
        
        # Compute confidence
        confidence = min(1.0, primary_score)
        
        # Generate reasons
        reasons = self._generate_reasons(block, primary)
        
        return BlockRole(
            block_id=block.block_id,
            primary_role=primary,
            secondary_role=secondary,
            confidence=round(confidence, 2),
            role_scores={k: round(v, 2) for k, v in scores.items()},
            reasons=reasons,
        )
    
    def analyze_blocks(
        self, 
        blocks: list[IntraBlockDiagnostic]
    ) -> list[BlockRole]:
        """Analyze all blocks and assign roles."""
        return [self.analyze_block(b) for b in blocks]
    
    def _compute_role_scores(
        self, 
        block: IntraBlockDiagnostic
    ) -> dict[str, float]:
        """Compute scores for each role."""
        tb = block.token_breakdown
        sp = block.structural_payload
        
        scores = {
            "DEFINE": 0.0,
            "IMPLEMENT": 0.0,
            "USE": 0.0,
            "EXPLAIN": 0.0,
            "SUPPORT": 0.0,
            "NOISE": 0.0,
        }
        
        # DEFINE: High signature, class/function definitions
        if sp.class_count > 0:
            scores["DEFINE"] += 0.5
        if sp.function_count > 0 and sp.method_count == 0:
            scores["DEFINE"] += 0.3
        if tb.signatures_pct > self.signature_threshold:
            scores["DEFINE"] += 0.3
        
        # IMPLEMENT: High code logic
        if tb.code_logic_pct > self.code_threshold:
            scores["IMPLEMENT"] += 0.5
        if tb.control_flow_pct > 10:
            scores["IMPLEMENT"] += 0.2
        if sp.method_count > 0:
            scores["IMPLEMENT"] += 0.3
        
        # EXPLAIN: High docstrings/comments
        if tb.docstrings_pct > self.docstring_threshold:
            scores["EXPLAIN"] += 0.5
        if tb.comments_pct > 20:
            scores["EXPLAIN"] += 0.3
        
        # USE: References other blocks (via identifier density)
        id_density = block.identifier_density.density_ratio
        if id_density > 0.5 and tb.code_logic_pct > 20:
            scores["USE"] += 0.4
        if len(block.identifier_density.top_repeated) > 5:
            scores["USE"] += 0.2
        
        # SUPPORT: Error handling, utilities
        if tb.error_handling_pct > 15:
            scores["SUPPORT"] += 0.4
        if "util" in block.file.lower() or "helper" in block.file.lower():
            scores["SUPPORT"] += 0.3
        
        # NOISE: High logging, low signal
        if tb.logging_pct > self.logging_threshold:
            scores["NOISE"] += 0.5
        if block.noise_ratio > 0.4:
            scores["NOISE"] += 0.3
        if block.signal_ratio < 0.3:
            scores["NOISE"] += 0.2
        
        return scores
    
    def _generate_reasons(
        self,
        block: IntraBlockDiagnostic,
        role: ExplanatoryRole
    ) -> list[str]:
        """Generate human-readable reasons for classification."""
        tb = block.token_breakdown
        sp = block.structural_payload
        reasons = []
        
        if role == ExplanatoryRole.DEFINE:
            if sp.class_count > 0:
                reasons.append(f"Contains {sp.class_count} class definition(s)")
            if sp.function_count > 0:
                reasons.append(f"Contains {sp.function_count} function definition(s)")
            if tb.signatures_pct > 20:
                reasons.append(f"High signature content ({tb.signatures_pct:.0f}%)")
        
        elif role == ExplanatoryRole.IMPLEMENT:
            if tb.code_logic_pct > 30:
                reasons.append(f"High code logic ({tb.code_logic_pct:.0f}%)")
            if sp.method_count > 0:
                reasons.append(f"Contains {sp.method_count} method(s)")
        
        elif role == ExplanatoryRole.EXPLAIN:
            if tb.docstrings_pct > 15:
                reasons.append(f"High docstring content ({tb.docstrings_pct:.0f}%)")
            if tb.comments_pct > 15:
                reasons.append(f"High comment content ({tb.comments_pct:.0f}%)")
        
        elif role == ExplanatoryRole.NOISE:
            if tb.logging_pct > 10:
                reasons.append(f"High logging ({tb.logging_pct:.0f}%)")
            if block.noise_ratio > 0.4:
                reasons.append(f"High noise ratio ({block.noise_ratio:.0%})")
        
        return reasons


def format_block_role(role: BlockRole) -> str:
    """Format block role for display."""
    lines = []
    
    lines.append(f"Block: {role.block_id}")
    lines.append(f"Primary Role: {role.primary_role.value}")
    
    if role.secondary_role:
        lines.append(f"Secondary Role: {role.secondary_role.value}")
    
    lines.append(f"Confidence: {role.confidence:.2f}")
    
    if role.reasons:
        lines.append("Reasons:")
        for reason in role.reasons:
            lines.append(f"  - {reason}")
    
    return "\n".join(lines)
