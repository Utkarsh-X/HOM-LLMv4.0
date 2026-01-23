"""
Module 4: Cognitive Load Estimation

Estimates mental effort required to understand each block.

Signals:
- Nesting depth
- Branching factor
- Identifier churn
- Implicit dependencies
- Role mismatch

CONSTRAINTS:
- Deterministic heuristics only
- No ML/LLM
- Read-only
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from diagnostics.context.inspect_context import IntraBlockDiagnostic
from diagnostics.context_level3.inspect_explanatory_roles import (
    BlockRole,
    ExplanatoryRole,
)
from diagnostics.common.utils import safe_divide


class LoadLevel(Enum):
    """Cognitive load level."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class BlockCognitiveLoad:
    """Cognitive load assessment for a block."""
    
    block_id: str
    load_level: LoadLevel
    load_score: float = 0.0  # 0-1, higher = more load
    
    # Contributing factors
    nesting_score: float = 0.0
    branching_score: float = 0.0
    identifier_churn: float = 0.0
    implicit_deps_score: float = 0.0
    role_mismatch_score: float = 0.0
    
    # Reasons
    reasons: list[str] = field(default_factory=list)


@dataclass
class CognitiveLoadResult:
    """Complete cognitive load analysis result."""
    
    # Per-block loads
    block_loads: list[BlockCognitiveLoad] = field(default_factory=list)
    
    # Summary
    high_load_count: int = 0
    medium_load_count: int = 0
    low_load_count: int = 0
    
    # Average load
    average_load_score: float = 0.0
    
    # Overall assessment
    overall_load: LoadLevel = LoadLevel.MEDIUM
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class CognitiveLoadAnalyzer:
    """
    Estimates cognitive load for context blocks.
    
    Uses deterministic signals:
    - Nesting depth from structural payload
    - Branching from control flow
    - Identifier density/churn
    - Role mismatches
    """
    
    # Thresholds
    HIGH_NESTING = 3
    HIGH_CONTROL_FLOW = 20  # % control flow
    HIGH_IDENTIFIER_DENSITY = 0.6
    
    def analyze(
        self,
        blocks: list[IntraBlockDiagnostic],
        roles: list[BlockRole]
    ) -> CognitiveLoadResult:
        """
        Analyze cognitive load for all blocks.
        
        Args:
            blocks: Level-1 diagnostics
            roles: Block roles from Module 2
            
        Returns:
            CognitiveLoadResult with load assessments
        """
        result = CognitiveLoadResult()
        
        # Create role lookup
        role_map = {r.block_id: r for r in roles}
        
        # Analyze each block
        for block in blocks:
            role = role_map.get(block.block_id)
            load = self._analyze_block_load(block, role)
            result.block_loads.append(load)
        
        # Compute summary
        for load in result.block_loads:
            if load.load_level == LoadLevel.HIGH:
                result.high_load_count += 1
            elif load.load_level == LoadLevel.MEDIUM:
                result.medium_load_count += 1
            else:
                result.low_load_count += 1
        
        # Average score
        if result.block_loads:
            result.average_load_score = (
                sum(l.load_score for l in result.block_loads) / 
                len(result.block_loads)
            )
        
        # Overall assessment
        if result.high_load_count >= 3:
            result.overall_load = LoadLevel.HIGH
        elif result.high_load_count >= 1 or result.average_load_score > 0.5:
            result.overall_load = LoadLevel.MEDIUM
        else:
            result.overall_load = LoadLevel.LOW
        
        # Warnings
        result.warnings = self._generate_warnings(result)
        
        return result
    
    def _analyze_block_load(
        self,
        block: IntraBlockDiagnostic,
        role: Optional[BlockRole]
    ) -> BlockCognitiveLoad:
        """Analyze cognitive load for a single block."""
        load = BlockCognitiveLoad(block_id=block.block_id, load_level=LoadLevel.LOW)
        
        sp = block.structural_payload
        tb = block.token_breakdown
        
        # 1. Nesting depth
        if sp.nested_depth_max >= self.HIGH_NESTING:
            load.nesting_score = min(1.0, sp.nested_depth_max / 5)
            load.reasons.append(f"Deep nesting (depth {sp.nested_depth_max})")
        
        # 2. Branching (control flow)
        if tb.control_flow_pct > self.HIGH_CONTROL_FLOW:
            load.branching_score = min(1.0, tb.control_flow_pct / 40)
            load.reasons.append(f"High branching ({tb.control_flow_pct:.0f}% control flow)")
        
        # 3. Identifier churn
        id_density = block.identifier_density.density_ratio
        if id_density > self.HIGH_IDENTIFIER_DENSITY:
            load.identifier_churn = min(1.0, id_density)
            load.reasons.append(f"High identifier density ({id_density:.2f})")
        
        # 4. Implicit dependencies
        # Heuristic: many unique identifiers but few repeats = implicit deps
        unique = block.identifier_density.total_unique
        repeated = len(block.identifier_density.top_repeated)
        if unique > 10 and repeated < 3:
            load.implicit_deps_score = 0.5
            load.reasons.append("Many implicit dependencies")
        
        # 5. Role mismatch
        if role:
            if (role.primary_role == ExplanatoryRole.IMPLEMENT and 
                role.secondary_role != ExplanatoryRole.DEFINE):
                # Implementation without nearby definition
                load.role_mismatch_score = 0.3
                load.reasons.append("Implementation without definition context")
        
        # Compute total score
        load.load_score = (
            load.nesting_score * 0.25 +
            load.branching_score * 0.25 +
            load.identifier_churn * 0.2 +
            load.implicit_deps_score * 0.15 +
            load.role_mismatch_score * 0.15
        )
        
        # Classify load level
        if load.load_score > 0.5:
            load.load_level = LoadLevel.HIGH
        elif load.load_score > 0.25:
            load.load_level = LoadLevel.MEDIUM
        else:
            load.load_level = LoadLevel.LOW
        
        return load
    
    def _generate_warnings(self, result: CognitiveLoadResult) -> list[str]:
        """Generate cognitive load warnings."""
        warnings = []
        
        if result.high_load_count >= 3:
            warnings.append(
                f"High cognitive load: {result.high_load_count} blocks exceed threshold"
            )
        
        if result.average_load_score > 0.6:
            warnings.append(
                f"Overall high cognitive burden (avg score: {result.average_load_score:.2f})"
            )
        
        # Find specific high-load blocks
        high_blocks = [l for l in result.block_loads if l.load_level == LoadLevel.HIGH]
        for load in high_blocks[:3]:
            if load.reasons:
                warnings.append(f"Block '{load.block_id}': {load.reasons[0]}")
        
        return warnings


def format_cognitive_load(result: CognitiveLoadResult) -> str:
    """Format cognitive load result for display."""
    lines = []
    
    lines.append(f"Cognitive Load: {result.overall_load.value}")
    lines.append(f"  HIGH: {result.high_load_count} blocks")
    lines.append(f"  MEDIUM: {result.medium_load_count} blocks")
    lines.append(f"  LOW: {result.low_load_count} blocks")
    lines.append(f"  Average score: {result.average_load_score:.2f}")
    
    # List high-load blocks
    high_blocks = [l for l in result.block_loads if l.load_level == LoadLevel.HIGH]
    if high_blocks:
        lines.append("")
        lines.append("High-load blocks:")
        for load in high_blocks[:5]:
            reasons = ", ".join(load.reasons) if load.reasons else "multiple factors"
            lines.append(f"  {load.block_id}: {reasons}")
    
    return "\n".join(lines)
