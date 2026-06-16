from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.target_file_selector import (
    EvidenceTargetFileSelector,
    TargetFileSelectionRequest,
)


def candidate(file_path: str, candidate_id: str, score: float) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        file_path=file_path,
        symbol_id=None,
        span_start=1,
        span_end=3,
        content_hash="hash",
        source_channels=("bm25",),
        bm25_score=score,
        vector_score=None,
        graph_score=None,
        retrieval_score=score,
        metadata={},
    )


def evidence_set(*candidates: EvidenceCandidate) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="evidence-1",
        query="fix target",
        candidates=candidates,
        diagnostics=RetrievalDiagnostics(
            bm25_count=len(candidates),
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )


def test_target_selector_selects_clear_highest_scoring_file() -> None:
    selector = EvidenceTargetFileSelector()

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(
                candidate("api/routes.py", "cand-1", 0.9),
                candidate("api/routes.py", "cand-2", 0.7),
                candidate("utils/helpers.py", "cand-3", 0.2),
            ),
        )
    )

    assert result.decision == "selected"
    assert result.target_file == "api/routes.py"
    assert result.confidence > 0.0
    assert result.candidate_file_scores["api/routes.py"] > result.candidate_file_scores[
        "utils/helpers.py"
    ]


def test_target_selector_returns_ambiguous_for_close_file_scores() -> None:
    selector = EvidenceTargetFileSelector(min_score_margin=0.15)

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(
                candidate("api/routes.py", "cand-1", 0.6),
                candidate("utils/helpers.py", "cand-2", 0.55),
            ),
        )
    )

    assert result.decision == "ambiguous"
    assert result.target_file is None
    assert result.reason == "top_file_scores_too_close"


def test_target_selector_returns_no_candidates_for_empty_evidence() -> None:
    selector = EvidenceTargetFileSelector()

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(),
        )
    )

    assert result.decision == "no_candidates"
    assert result.target_file is None
    assert result.reason == "evidence_set_has_no_candidates"


def test_target_selector_uses_query_path_tokens_to_break_close_scores() -> None:
    selector = EvidenceTargetFileSelector(min_score_margin=0.15)

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(
                candidate("utils/string_tools.py", "cand-1", 0.60),
                candidate("utils/validators.py", "cand-2", 0.55),
            ),
        )
    )

    assert result.decision == "ambiguous"

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=EvidenceSet(
                evidence_set_id="evidence-1",
                query="utils validators validate_email consecutive dots local part rejection",
                candidates=(
                    candidate("utils/string_tools.py", "cand-1", 0.60),
                    candidate("utils/validators.py", "cand-2", 0.55),
                ),
                diagnostics=evidence_set().diagnostics,
            ),
        )
    )

    assert result.decision == "selected"
    assert result.target_file == "utils/validators.py"
