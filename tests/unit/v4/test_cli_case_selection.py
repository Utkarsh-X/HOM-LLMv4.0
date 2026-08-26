"""Tests for the ``eval-swebench-lite`` case-selection helpers.

``_flatten_case_ids`` merges repeated/comma-separated ``--case-id`` values so
single-task and explicit batch selections share one flag;
``_deterministic_subset`` down-selects a pool deterministically for a fixed
seed while preserving fixture order.
"""

from homllm_v4.cli import _deterministic_subset, _flatten_case_ids


def test_flatten_case_ids_returns_none_for_missing_flag() -> None:
    assert _flatten_case_ids(None) is None


def test_flatten_case_ids_accepts_repeated_flags() -> None:
    assert _flatten_case_ids(("a-1", "b-2")) == ("a-1", "b-2")


def test_flatten_case_ids_splits_comma_separated_values() -> None:
    raw = ["sympy__sympy-21614,sympy__sympy-21627"]
    assert _flatten_case_ids(raw) == ("sympy__sympy-21614", "sympy__sympy-21627")


def test_flatten_case_ids_merges_mixed_repeated_and_comma_forms() -> None:
    raw = ["a-1,b-2", " c-3 "]
    assert _flatten_case_ids(raw) == ("a-1", "b-2", "c-3")


def test_flatten_case_ids_drops_blank_segments() -> None:
    assert _flatten_case_ids(("a-1", "", "  ", " , ,b-2,")) == ("a-1", "b-2")
    assert _flatten_case_ids(()) is None
    assert _flatten_case_ids(["", "   "]) is None


def test_deterministic_subset_returns_full_pool_without_effective_limit() -> None:
    pool = ("b-case", "a-case", "c-case")
    assert _deterministic_subset(pool, limit=None, sample_seed=7) == pool
    assert _deterministic_subset(pool, limit=0, sample_seed=7) == pool
    assert _deterministic_subset(pool, limit=-1, sample_seed=7) == pool
    assert _deterministic_subset(pool, limit=3, sample_seed=7) == pool
    assert _deterministic_subset(pool, limit=10, sample_seed=7) == pool


def test_deterministic_subset_downselects_to_limit_entries() -> None:
    pool = tuple(f"case-{index:02d}" for index in range(40))

    subset = _deterministic_subset(pool, limit=12, sample_seed=20260824)

    assert len(subset) == 12
    assert set(subset) <= set(pool)
    assert len(set(subset)) == 12


def test_deterministic_subset_is_stable_for_fixed_seed() -> None:
    pool = tuple(f"case-{index:02d}" for index in range(40))

    assert _deterministic_subset(pool, 12, 20260824) == _deterministic_subset(
        pool, 12, 20260824
    )


def test_deterministic_subset_preserves_fixture_order_over_sorted_order() -> None:
    pool = ("zeta", "kilo", "alpha", "mike", "bravo")

    subset = _deterministic_subset(pool, limit=3, sample_seed=20260824)

    positions = [pool.index(case_id) for case_id in subset]
    assert positions == sorted(positions)


def test_deterministic_subset_varies_with_seed() -> None:
    pool = tuple(f"case-{index:02d}" for index in range(100))

    assert _deterministic_subset(pool, 10, 1) != _deterministic_subset(pool, 10, 2)
