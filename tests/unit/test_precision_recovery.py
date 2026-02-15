"""Unit tests for deterministic precision recovery."""

from homllm.retrieval.interfaces import Candidate, RetrievalConfig
from homllm.retrieval.precision_recovery import PrecisionRecovery


class _StubBM25:
    def __init__(self, mapping: dict[str, list[Candidate]]):
        self.mapping = mapping

    def search(self, query: str, top_k: int) -> list[Candidate]:
        return list(self.mapping.get(query, []))[:top_k]


class _StubVector:
    def __init__(self, mapping: dict[str, list[Candidate]]):
        self.mapping = mapping

    def search(self, query: str, top_k: int) -> list[Candidate]:
        return list(self.mapping.get(query, []))[:top_k]


def _cfg(**overrides) -> RetrievalConfig:
    cfg = RetrievalConfig(
        bm25_top_k=50,
        vector_top_k=50,
        hybrid_method="rrf",
        rrf_k=10,
        bm25_weight=0.5,
        vector_weight=0.5,
        expansion_enabled=False,
        expansion_max_additions=4,
        expansion_min_similarity=0.25,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    cfg.__post_init__()
    return cfg


def _base_candidates() -> list[Candidate]:
    return [
        Candidate(
            doc_id="doc_main_1",
            file="pkg/main.py",
            symbol_id="sym:main_one",
            content="def main_one():\n    missing_helper()\n    return True",
            hybrid_score=0.9,
            provenance=("bm25",),
        ),
        Candidate(
            doc_id="doc_main_2",
            file="pkg/main.py",
            symbol_id="sym:main_two",
            content="def main_two():\n    second_helper()\n    return True",
            hybrid_score=0.8,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_3",
            file="pkg/main.py",
            symbol_id="sym:main_three",
            content="def main_three():\n    pass",
            hybrid_score=0.7,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_4",
            file="pkg/main.py",
            symbol_id="sym:main_four",
            content="def main_four():\n    pass",
            hybrid_score=0.6,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_5",
            file="pkg/main.py",
            symbol_id="sym:main_five",
            content="def main_five():\n    pass",
            hybrid_score=0.5,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_6",
            file="pkg/main.py",
            symbol_id="sym:main_six",
            content="def main_six():\n    pass",
            hybrid_score=0.4,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_7",
            file="pkg/main.py",
            symbol_id="sym:main_seven",
            content="def main_seven():\n    pass",
            hybrid_score=0.3,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_8",
            file="pkg/main.py",
            symbol_id="sym:main_eight",
            content="def main_eight():\n    pass",
            hybrid_score=0.2,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_9",
            file="pkg/main.py",
            symbol_id="sym:main_nine",
            content="def main_nine():\n    pass",
            hybrid_score=0.1,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_main_10",
            file="pkg/main.py",
            symbol_id="sym:main_ten",
            content="def main_ten():\n    pass",
            hybrid_score=0.05,
            provenance=("vector",),
        ),
    ]


def test_precision_recovery_disabled_is_noop():
    recovery = PrecisionRecovery(_StubBM25({}), _StubVector({}))
    candidates = _base_candidates()
    config = _cfg(precision_recovery_enabled=False)

    out = recovery.recover(candidates, "find helper", config, max_additions=3)

    assert out == candidates
    assert recovery.last_metrics["precision_recovery_added"] == 0


def test_precision_recovery_enforces_hard_and_ratio_caps():
    helper_candidates = [
        Candidate(
            doc_id=f"doc_helper_{i}",
            file="pkg/helpers.py",
            symbol_id=f"sym:helper_{i}",
            content=f"def helper_{i}():\n    pass",
            bm25_score=100 - i,
            provenance=("bm25",),
        )
        for i in range(8)
    ]
    bm25 = _StubBM25(
        {
            "helper_0": helper_candidates,
            "helper_1": helper_candidates,
            "helper_2": helper_candidates,
        }
    )
    recovery = PrecisionRecovery(bm25, _StubVector({}))
    base = _base_candidates()
    # 10 candidates -> ratio cap floor(10*0.2)=2; hard cap min(max_additions=10, config=10, 5)=5 => effective 2.
    cfg = _cfg(
        precision_recovery_enabled=True,
        precision_recovery_max_additions=10,
        precision_recovery_max_ratio=0.2,
        precision_recovery_scan_candidates=2,
        precision_recovery_identifier_limit=16,
        precision_recovery_min_confidence=0.0,
    )
    # Ensure identifiers extracted include helper names.
    base[0] = Candidate(
        doc_id=base[0].doc_id,
        file=base[0].file,
        symbol_id=base[0].symbol_id,
        content="def main_one():\n    helper_0()\n    helper_1()\n    helper_2()",
        bm25_score=base[0].bm25_score,
        vector_score=base[0].vector_score,
        hybrid_score=base[0].hybrid_score,
        provenance=base[0].provenance,
        granularity_level=base[0].granularity_level,
        span_start=base[0].span_start,
        span_end=base[0].span_end,
        parent_symbol_id=base[0].parent_symbol_id,
        entity_ids=base[0].entity_ids,
        doc_type=base[0].doc_type,
        semantic_embedding=base[0].semantic_embedding,
    )

    out = recovery.recover(base, "", cfg, max_additions=10)
    added = [c for c in out if c.doc_id.startswith("doc_helper_")]

    assert len(added) == 2
    assert recovery.last_metrics["precision_recovery_cap"] == 2
    assert recovery.last_metrics["precision_recovery_added"] == 2


def test_precision_recovery_is_deterministic():
    bm25 = _StubBM25(
        {
            "missing_helper": [
                Candidate(
                    doc_id="doc_helper",
                    file="pkg/helpers.py",
                    symbol_id="sym:missing_helper",
                    content="def missing_helper():\n    return 1",
                    bm25_score=9.0,
                    provenance=("bm25",),
                )
            ]
        }
    )
    recovery = PrecisionRecovery(bm25, _StubVector({}))
    base = _base_candidates()
    cfg = _cfg(
        precision_recovery_enabled=True,
        precision_recovery_max_additions=3,
        precision_recovery_max_ratio=0.2,
        precision_recovery_scan_candidates=2,
        precision_recovery_identifier_limit=4,
    )

    out1 = recovery.recover(base, "find helper", cfg, max_additions=3)
    out2 = recovery.recover(base, "find helper", cfg, max_additions=3)

    assert [c.doc_id for c in out1] == [c.doc_id for c in out2]
    assert [c.provenance for c in out1] == [c.provenance for c in out2]


def test_precision_recovery_provenance_and_confidence_metrics():
    bm25 = _StubBM25(
        {
            "missing_helper": [
                Candidate(
                    doc_id="doc_helper",
                    file="pkg/helpers.py",
                    symbol_id="sym:missing_helper",
                    content="def missing_helper():\n    return 1",
                    bm25_score=8.0,
                    provenance=("bm25",),
                )
            ]
        }
    )
    recovery = PrecisionRecovery(bm25, _StubVector({}))
    base = _base_candidates()
    cfg = _cfg(
        precision_recovery_enabled=True,
        precision_recovery_scan_candidates=1,
        precision_recovery_identifier_limit=8,
    )

    out = recovery.recover(base, "", cfg, max_additions=3)
    added = [c for c in out if c.doc_id == "doc_helper"]

    assert len(added) == 1
    assert added[0].provenance[0].startswith("precision_recovery:bm25_exact:")
    assert recovery.last_metrics["precision_recovery_conf_mean"] == 1.0
    assert recovery.last_metrics["precision_recovery_conf_min"] == 1.0
    assert recovery.last_metrics["precision_recovery_conf_max"] == 1.0


def test_precision_recovery_confidence_gate_blocks_low_confidence():
    vector = _StubVector(
        {
            "definition missing_helper": [
                Candidate(
                    doc_id="doc_vector_helper",
                    file="pkg/helpers.py",
                    symbol_id="sym:other_name",
                    content="def other_name():\n    return 1",
                    vector_score=0.79,
                    provenance=("vector",),
                )
            ]
        }
    )
    recovery = PrecisionRecovery(_StubBM25({}), vector)
    base = _base_candidates()
    cfg = _cfg(
        precision_recovery_enabled=True,
        precision_recovery_scan_candidates=1,
        precision_recovery_identifier_limit=2,
        precision_recovery_min_confidence=0.8,
    )

    out = recovery.recover(base, "find helper", cfg, max_additions=3)
    assert all(c.doc_id != "doc_vector_helper" for c in out)
