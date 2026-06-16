from homllm_v4.contracts.evidence import EvidenceSet


def candidate_overlap_ratio(
    previous: EvidenceSet,
    current: EvidenceSet,
    *,
    top_n: int = 20,
) -> float:
    previous_ids = tuple(candidate.candidate_id for candidate in previous.candidates[:top_n])
    current_ids = tuple(candidate.candidate_id for candidate in current.candidates[:top_n])
    if not previous_ids or not current_ids:
        return 0.0
    overlap = len(set(previous_ids).intersection(current_ids))
    denominator = min(len(previous_ids), len(current_ids), top_n)
    return round(overlap / float(denominator), 3)


def is_repeated_retrieval(
    previous: EvidenceSet,
    current: EvidenceSet,
    *,
    previous_sufficiency_score: float,
    current_sufficiency_score: float,
    threshold: float = 0.8,
    top_n: int = 20,
) -> bool:
    overlap = candidate_overlap_ratio(previous, current, top_n=top_n)
    improved = current_sufficiency_score > previous_sufficiency_score
    return overlap >= threshold and not improved
