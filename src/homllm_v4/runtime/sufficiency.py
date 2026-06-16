from homllm_v4.contracts.context import ContextPack
from homllm_v4.contracts.evidence import EvidenceSet
from homllm_v4.contracts.loop import SufficiencyDecision


class DeterministicSufficiencyChecker:
    def check(
        self,
        *,
        evidence_set: EvidenceSet,
        context_pack: ContextPack,
        min_candidates: int,
        min_context_blocks: int,
    ) -> SufficiencyDecision:
        candidate_count = len(evidence_set.candidates)
        block_count = len(context_pack.blocks)
        missing: list[str] = []
        if candidate_count == 0:
            missing.append("empty_evidence")
        if candidate_count < min_candidates:
            missing.append("insufficient_candidates")
        if block_count < min_context_blocks:
            missing.append("insufficient_context_blocks")

        candidate_score = min(candidate_count / max(min_candidates, 1), 1.0)
        block_score = min(block_count / max(min_context_blocks, 1), 1.0)
        score = round((candidate_score + block_score) / 2.0, 3)
        return SufficiencyDecision(
            sufficient=not missing,
            score=score,
            missing_reasons=tuple(missing),
            evidence_candidate_count=candidate_count,
            context_block_count=block_count,
        )


def insufficient_decision(reason: str) -> SufficiencyDecision:
    return SufficiencyDecision(
        sufficient=False,
        score=0.0,
        missing_reasons=(reason,),
        evidence_candidate_count=0,
        context_block_count=0,
    )
