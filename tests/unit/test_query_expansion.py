"""Unit tests for deterministic lexical query expansion."""

from homllm.common.types import Intent
from homllm.retrieval.interfaces import RetrievalConfig
from homllm.retrieval.preparer import SimpleQueryPreparer
from homllm.retrieval.query_expansion import DeterministicQueryExpander


def _config(**overrides) -> RetrievalConfig:
    base = dict(
        bm25_top_k=50,
        vector_top_k=50,
        hybrid_method="rrf",
        rrf_k=10,
        bm25_weight=0.5,
        vector_weight=0.5,
        expansion_enabled=True,
        expansion_max_additions=4,
        expansion_min_similarity=0.25,
    )
    base.update(overrides)
    return RetrievalConfig(**base)


def test_expander_is_deterministic_and_capped():
    expander = DeterministicQueryExpander(
        enabled=True,
        max_terms=3,
        min_token_length=3,
        synonyms={
            "login": ("signin", "authentication", "auth"),
            "function": ("method", "routine"),
        },
    )
    base_terms = ["login", "function", "login"]
    out1, added1 = expander.expand(base_terms)
    out2, added2 = expander.expand(base_terms)

    assert out1 == out2
    assert added1 == added2
    assert len(added1) == 3
    assert out1 == ["login", "function", "signin", "authentication", "auth"]


def test_expander_disabled_keeps_base_terms():
    expander = DeterministicQueryExpander(
        enabled=False,
        max_terms=5,
        min_token_length=3,
        synonyms={"login": ("signin",)},
    )
    expanded, added = expander.expand(["login", "module"])
    assert expanded == ["login", "module"]
    assert added == ()


def test_preparer_expands_lexical_terms_only_dense_query_unchanged():
    preparer = SimpleQueryPreparer(
        _config(
            query_expansion_enabled=True,
            query_expansion_max_terms=4,
            query_expansion_synonyms={
                "login": ["signin", "authentication"],
                "function": ["method"],
            },
        )
    )
    query = "find login function in auth module"
    prepared = preparer.prepare(query, Intent.SEARCH)

    assert prepared.dense_query == query
    assert "signin" in prepared.lexical_terms
    assert "authentication" in prepared.lexical_terms
    assert "method" in prepared.lexical_terms
    assert prepared.lexical_expansion_terms == ("signin", "authentication", "method")


def test_preparer_expansion_cap_enforced():
    preparer = SimpleQueryPreparer(
        _config(
            query_expansion_enabled=True,
            query_expansion_max_terms=2,
            query_expansion_synonyms={
                "auth": ["authentication", "authorize", "authorization"],
                "module": ["package", "file"],
            },
        )
    )
    prepared = preparer.prepare("auth module lookup", Intent.SEARCH)

    assert len(prepared.lexical_expansion_terms) == 2
    assert prepared.lexical_expansion_terms == ("authentication", "authorize")
