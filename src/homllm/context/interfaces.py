"""Protocols and interfaces for Context Assembly layer."""

from dataclasses import dataclass
from typing import Protocol

from homllm.ranking.interfaces import DebugTrace
from homllm.retrieval.interfaces import Candidate


@dataclass(frozen=True)
class ContextBlock:
    """A block of code to include in context."""

    block_id: str
    file: str
    start_line: int
    end_line: int
    content: str
    symbol_id: str | None
    symbol_name: str | None
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class ScoredBlock:
    """Context block with scoring signals."""

    block: ContextBlock
    semantic_score: float  # From reranker
    name_score: float  # Identifier overlap
    structural_priority: float  # Entrypoint/decorator weight
    novelty_score: float  # Difference from selected
    coherence_score: float  # Fit with current context
    final_score: float  # Combined score


@dataclass(frozen=True)
class AllocatedBlock:
    """Block with allocated token budget."""

    block: ContextBlock
    allocated_tokens: int
    truncated_content: str  # Content after token budget allocation


@dataclass(frozen=True)
class ContextArtifact:
    """Final context artifact for generation."""

    query_id: str
    context_text: str  # Stitched content
    blocks: tuple[ContextBlock, ...]  # id, file, start, end, tokens
    token_budget: int
    used_tokens: int
    provenance: dict  # Full trace
    explain_trace: tuple[str, ...]  # Selection rationale


@dataclass
class BudgetConfig:
    """Budget manager configuration."""

    max_tokens: int
    budget_mode: str  # "adaptive" or "fixed"
    structural_priority_multiplier: float = 1.5


@dataclass
class ContextConfig:
    """Context assembly configuration."""

    max_tokens: int
    budget_mode: str
    summarization_enabled: bool
    ordering: str  # "structural_first" or "score_first"
    structural_priority_multiplier: float = 1.5
    generation_reserve_tokens: int = 800  # Tokens reserved for generation output (~20% of context)
    # Block scoring weights (all from config, no hardcoded values)
    w_semantic: float = 0.4
    w_name: float = 0.2
    w_structural: float = 0.2
    w_novelty: float = 0.1
    w_coherence: float = 0.1
    # Structural priority bonuses (all from config)
    structural_priority_entrypoint_bonus: float = 0.5
    structural_priority_decorator_bonus: float = 0.3
    structural_priority_callgraph_bonus: float = 0.2
    structural_priority_cap: float = 1.0
    # Coherence bonuses (all from config)
    coherence_same_file_bonus: float = 0.8
    coherence_different_file_bonus: float = 0.5
    ranking_surface_lock_enabled: bool = True
    # Tier 2: Coherence refinement (post-lock, mid-range only)
    coherence_enabled: bool = True
    coherence_max_contribution: float = 0.15      # Max 15% of base score
    coherence_protect_top_n: int = 3               # Never reorder top N
    coherence_proximity_lines: int = 50            # Same-file adjacency window
    coherence_synergy_threshold: float = 0.3       # Jaccard threshold for synergy
    coherence_dispersion_threshold: float = 0.9    # File/block ratio penalty trigger
    coherence_callgraph_bonus: float = 0.1         # Caller-callee adjacency bonus
    # Tier 3B: Submodular context packer
    submodular_packer_enabled: bool = False
    submodular_w_rrf: float = 0.40
    submodular_w_novelty: float = 0.20
    submodular_w_graph: float = 0.20
    submodular_w_concept: float = 0.20
    submodular_min_density_epsilon: float = 0.001
    submodular_novelty_scaling: str = "none"  # "none" or "file_concentration"
    submodular_noise_guard_enabled: bool = False
    submodular_noise_guard_min_file_ratio: float = 0.60
    submodular_noise_guard_rrf_ratio_threshold: float = 0.85
    # Tier 3B: Dynamic budget expansion (optional)
    dynamic_budget_enabled: bool = False
    dynamic_budget_trigger_used_pct: float = 0.80
    dynamic_budget_min_budget_limited_tokens: int = 128
    dynamic_budget_safety_margin_tokens: int = 192
    dynamic_budget_step_tokens: int = 400
    dynamic_budget_max_expansions: int = 2
    dynamic_budget_max_extra_tokens: int = 1200
    dynamic_budget_tail_density_ratio_trigger: float = 0.65
    # Tier 3B: Relevance safety guard
    relevance_gate_enabled: bool = False
    relevance_gate_threshold: float = 0.25
    # Tier 3C: Precision filter (remove low-signal cross-component spillover)
    precision_filter_enabled: bool = False
    precision_filter_query_identifier_min: int = 1
    precision_filter_low_score_threshold: float = 0.25
    precision_filter_min_kept_blocks: int = 10
    # Tier 3C: Sparse-context backfill (coverage safety for under-filled contexts)
    sparse_backfill_enabled: bool = False
    sparse_backfill_min_utilization: float = 0.45
    sparse_backfill_min_blocks: int = 18
    sparse_backfill_max_additional_blocks: int = 10
    # Claim-gain epsilon swap (post-packer, low-risk tie-break)
    claim_gain_swap_enabled: bool = False
    claim_gain_swap_score_epsilon: float = 0.02
    claim_gain_swap_max_swaps: int = 2
    claim_gain_swap_min_relevance_floor: float = 0.25
    # Unresolved-evidence injection (post-selection, budget-safe override)
    unresolved_evidence_injection_enabled: bool = False
    unresolved_evidence_injection_max_blocks: int = 2
    unresolved_evidence_injection_min_claim_gain: float = 0.1
    unresolved_evidence_injection_relevance_floor: float = 0.15
    unresolved_evidence_injection_max_token_share: float = 0.15
    unresolved_evidence_injection_replace_from_tail: bool = True
    # Tier 3B: Sufficiency escape hatch
    escape_hatch_enabled: bool = False


class BlockScorer(Protocol):
    """Protocol for scoring context blocks."""

    def score(
        self,
        blocks: list[ContextBlock],
        query: str,
        selected_blocks: list[ContextBlock],
        debug_traces: dict[str, DebugTrace],
    ) -> list[ScoredBlock]:
        """
        Score blocks for context selection.
        
        Signals:
        - semantic_score: From reranker
        - name_score: Identifier overlap
        - structural_priority: Entrypoint/decorator weight
        - novelty_score: Difference from selected
        - coherence_score: Fit with current context
        """
        ...


class BudgetManager(Protocol):
    """Protocol for token budget allocation."""

    def allocate(
        self,
        blocks: list[ScoredBlock],
        query_features: dict,  # Query metadata
        config: BudgetConfig,
        tokenizer: object,  # Tokenizer for exact counting
        preserve_order: bool = False,
    ) -> list[AllocatedBlock]:
        """
        Assigns token budgets per block.
        
        Guarantees:
        - sum(allocated_tokens) <= config.max_tokens
        - Structural blocks prioritized
        - Uses same tokenizer as generation model
        """
        ...


class Stitcher(Protocol):
    """Protocol for stitching blocks into final context."""

    def stitch(
        self,
        blocks: list[AllocatedBlock],
        query: str,
        ordering: str,
        preserve_order: bool = False,
    ) -> str:
        """
        Stitch blocks into final context text.
        
        Order:
        1. Query brief (one-line restatement)
        2. Structural blocks (decorators, entrypoints) in call-order
        3. Core implementation (functions, classes) by priority
        4. Helper functions
        5. Peripheral (tests, configs, summaries)
        6. Provenance appendix
        """
        ...
