"""Claim-coverage gate package."""

from homllm.claim_coverage.extractor import extract_claim_packet
from homllm.claim_coverage.gate import (
    build_unresolved_claim_queries,
    coverage_summary_to_prompt_text,
    decide_gate_action,
    evidence_map_to_prompt_text,
    packet_to_prompt_text,
    run_claim_coverage,
    to_serializable_dict,
)
from homllm.claim_coverage.interfaces import (
    Claim,
    ClaimCoverage,
    ClaimCoverageConfig,
    ClaimIntent,
    ClaimPacket,
    CoverageReport,
    EvidenceAnchor,
    GateAction,
    GateDecision,
)
from homllm.claim_coverage.scorer import score_claim_coverage

__all__ = [
    "Claim",
    "ClaimCoverage",
    "ClaimCoverageConfig",
    "ClaimIntent",
    "ClaimPacket",
    "CoverageReport",
    "EvidenceAnchor",
    "GateAction",
    "GateDecision",
    "extract_claim_packet",
    "score_claim_coverage",
    "run_claim_coverage",
    "decide_gate_action",
    "build_unresolved_claim_queries",
    "packet_to_prompt_text",
    "evidence_map_to_prompt_text",
    "coverage_summary_to_prompt_text",
    "to_serializable_dict",
]
