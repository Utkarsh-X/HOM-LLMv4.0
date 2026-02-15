"""Unit tests for retrieval query preparation contracts."""

from homllm.common.types import Intent
from homllm.indexer.embedder import QUERY_EMBED_INSTRUCTION
from homllm.retrieval.preparer import SimpleQueryPreparer


def test_dense_query_is_raw_and_not_prefixed():
    preparer = SimpleQueryPreparer()
    query = "find authentication function in login service"

    prepared = preparer.prepare(query, Intent.SEARCH)

    assert prepared.dense_query == query
    assert QUERY_EMBED_INSTRUCTION not in prepared.dense_query


def test_lexical_terms_exclude_stop_words():
    preparer = SimpleQueryPreparer()

    prepared = preparer.prepare(
        "find the auth function in the login module",
        Intent.SEARCH,
    )

    assert "the" not in prepared.lexical_terms
    assert "find" in prepared.lexical_terms
    assert "auth" in prepared.lexical_terms
