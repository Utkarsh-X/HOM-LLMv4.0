from homllm.context.interfaces import ContextArtifact, ContextBlock
from homllm.generation.hallucination import HallucinationDetector


def _artifact_with_symbol(symbol_name: str) -> ContextArtifact:
    block = ContextBlock(
        block_id="b1",
        file="pkg/example.py",
        start_line=10,
        end_line=20,
        content="def sample_function():\n    pass\n",
        symbol_id="s1",
        symbol_name=symbol_name,
        provenance=("bm25",),
    )
    return ContextArtifact(
        query_id="q1",
        context_text=block.content,
        blocks=(block,),
        token_budget=100,
        used_tokens=10,
        provenance={},
        explain_trace=(),
    )


def test_detector_ignores_sentence_words_and_flags_code_like_identifiers():
    detector = HallucinationDetector()
    artifact = _artifact_with_symbol("RedisClient")

    flags = detector.detect(
        "This answer says RedisClient calls WorkerPool and PostgresAdapter.",
        artifact,
    )

    assert "identifier_not_in_context: This" not in flags
    assert "identifier_not_in_context: WorkerPool" in flags
    assert "identifier_not_in_context: PostgresAdapter" in flags


def test_detector_flags_constant_case_but_not_plain_capitalized_words():
    detector = HallucinationDetector()
    artifact = _artifact_with_symbol("QueryOptimizer")

    flags = detector.detect(
        "Priority order is PREDICATE_PUSHDOWN before CONSTANT_FOLDING.",
        artifact,
    )

    assert "identifier_not_in_context: Priority" not in flags
    assert "identifier_not_in_context: PREDICATE_PUSHDOWN" in flags
    assert "identifier_not_in_context: CONSTANT_FOLDING" in flags
