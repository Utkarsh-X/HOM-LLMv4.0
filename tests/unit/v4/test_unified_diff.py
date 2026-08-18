"""Tests for the tolerant unified-diff applier (SWE-bench gold patches)."""

import pytest

from homllm_v4.utils.unified_diff import apply_unified_diff


def _patch(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_applies_simple_context_hunk() -> None:
    content = "line1\nline2\nline3\nline4\nline5\n"
    patch = _patch(
        "--- a/file.py",
        "+++ b/file.py",
        "@@ -2,3 +2,4 @@",
        " line2",
        "-line3",
        "+line3-fixed",
        " line4",
    )
    assert apply_unified_diff(content, patch) == "line1\nline2\nline3-fixed\nline4\nline5\n"


def test_applies_insertion_at_start() -> None:
    content = "line1\nline2\n"
    patch = _patch(
        "@@ -0,0 +1,2 @@",
        "+import os",
        "+import sys",
    )
    assert apply_unified_diff(content, patch) == "import os\nimport sys\nline1\nline2\n"


def test_applies_deletion_at_end() -> None:
    content = "line1\nline2\nline3\n"
    patch = _patch(
        "@@ -2,2 +2,1 @@",
        " line2",
        "-line3",
    )
    assert apply_unified_diff(content, patch) == "line1\nline2\n"


def test_handles_crlf_content_and_patch() -> None:
    content = "line1\r\nline2\r\nline3\r\n"
    patch = _patch(
        "@@ -2,1 +2,2 @@",
        " line2",
        "+line2.5",
    )
    assert apply_unified_diff(content, patch) == "line1\nline2\nline2.5\nline3\n"


def test_multiple_hunks_applied_bottom_up() -> None:
    content = "a1\na2\na3\nb1\nb2\nb3\nc1\nc2\nc3\n"
    patch = _patch(
        "@@ -1,2 +1,3 @@",
        " a1",
        " a2",
        "+a-extra",
        "@@ -7,2 +8,3 @@",
        " c1",
        " c2",
        "+c-extra",
    )
    assert apply_unified_diff(content, patch) == (
        "a1\na2\na-extra\na3\nb1\nb2\nb3\nc1\nc2\nc-extra\nc3\n"
    )


def test_tolerates_wrong_hunk_counts_like_git_recount() -> None:
    # SWE-bench patches are known to carry slightly wrong -a,b +c,d counts.
    # The applier trusts the body and start line (git apply --recount semantics).
    content = "ctx1\nctx2\nctx3\nctx4\nctx5\nctx6\nctx7\n"
    patch = _patch(
        "@@ -2,6 +2,10 @@",
        " ctx2",
        " ctx3",
        " ctx4",
        "+added-line",
        " ctx5",
    )
    assert apply_unified_diff(content, patch) == (
        "ctx1\nctx2\nctx3\nctx4\nadded-line\nctx5\nctx6\nctx7\n"
    )


def test_finds_hunk_near_expected_position() -> None:
    # Header start line is slightly off; the body still matches nearby.
    content = "a\nb\nc\nd\ne\nf\ng\n"
    patch = _patch(
        "@@ -5,3 +5,3 @@",
        " c",
        " d",
        " e",
    )
    # Header claims line 5 but the body (c,d,e) is at 3 — must still apply.
    assert apply_unified_diff(content, patch) == content


def test_tolerates_no_newline_marker() -> None:
    content = "one\ntwo\nthree\n"
    patch = _patch(
        "@@ -1,3 +1,3 @@",
        " one",
        " two",
        "-three",
        "+three!",
        "\\ No newline at end of file",
    )
    assert apply_unified_diff(content, patch) == "one\ntwo\nthree!\n"


def test_no_trailing_newline_in_input_stays_absent() -> None:
    content = "one\ntwo\nthree"
    patch = _patch(
        "@@ -1,2 +1,2 @@",
        " one",
        " two",
    )
    assert apply_unified_diff(content, patch) == "one\ntwo\nthree"


def test_pure_insertion_after_context() -> None:
    content = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
    patch = _patch(
        "@@ -4,2 +4,5 @@",
        " def bar():",
        "     return 2",
        "+    # trailing comment",
    )
    assert apply_unified_diff(content, patch) == (
        "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n    # trailing comment\n"
    )


def test_raises_on_context_mismatch() -> None:
    content = "aaa\nbbb\nccc\n"
    patch = _patch(
        "@@ -1,1 +1,2 @@",
        " not-in-content",
        "+added",
    )
    with pytest.raises(ValueError, match="hunk_context_mismatch"):
        apply_unified_diff(content, patch)


def test_raises_on_empty_patch() -> None:
    with pytest.raises(ValueError, match="no_hunks_found"):
        apply_unified_diff("abc\n", "diff --git a/x b/x\n--- a/x\n+++ b/x\n")


def test_finds_hunk_with_model_scale_line_number_drift() -> None:
    # Small models count hunk line numbers by hand and drift by tens of
    # lines. The default search window must absorb that drift while the
    # exact body match keeps the position unambiguous.
    lines = [f"line_{index:03d}" for index in range(90)]
    content = "\n".join(lines) + "\n"
    patch = _patch(
        "--- a/file.py",
        "+++ b/file.py",
        "@@ -70,3 +70,4 @@",
        " line_030",
        " line_031",
        "-line_032",
        "+line_032-fixed",
    )
    # Header claims line 70 but the body lives at line 31: a 39-line drift
    # beyond the old 30-line window. Must apply.
    expected = lines[:32] + ["line_032-fixed"] + lines[33:]
    assert apply_unified_diff(content, patch) == "\n".join(expected) + "\n"


def test_raises_when_hunk_drift_exceeds_search_window() -> None:
    lines = [f"line_{index:03d}" for index in range(90)]
    content = "\n".join(lines) + "\n"
    patch = _patch(
        "@@ -5,3 +5,3 @@",
        " line_080",
        " line_081",
        " line_082",
    )
    # Body absent from the file entirely: the applier must fail loudly, not
    # corrupt. (A body that exists exactly once far away now applies via the
    # full-file fallback, covered by the distant-hunk test below.)
    missing_body = _patch(
        "@@ -5,3 +5,3 @@",
        " zzz_not_in_file_080",
        " zzz_not_in_file_081",
        " zzz_not_in_file_082",
    )
    with pytest.raises(ValueError, match="hunk_context_mismatch"):
        apply_unified_diff(content, missing_body)


def test_falls_back_to_full_file_search_for_distant_hunk() -> None:
    # A model counting lines in a multi-thousand-line file can drift by
    # hundreds. When the windowed search misses, an unambiguous exact body
    # match anywhere in the file must still apply -- line numbers become
    # advisory, the body is authoritative.
    lines = [f"line_{index:03d}" for index in range(200)]
    lines[150:153] = ["def target():", "    return 1", ""]
    content = "\n".join(lines) + "\n"
    patch = _patch(
        "@@ -5,4 +5,7 @@",
        " def target():",
        "     return 1",
        " ",
        "+    return 2",
    )
    # Header claims line 5; the body lives near line 150 -- far beyond the
    # window. The single exact body match must win.
    applied = apply_unified_diff(content, patch)
    assert "def target():\n    return 1\n\n    return 2\n" in applied


def test_full_file_fallback_refuses_ambiguous_body() -> None:
    # A two-line body that appears in several places must fail loudly rather
    # than guess which occurrence the model meant.
    lines = [f"filler_{index:03d}" for index in range(300)]
    lines[100] = "def f():"
    lines[101] = "    pass"
    lines[200] = "def f():"
    lines[201] = "    pass"
    content = "\n".join(lines) + "\n"
    patch = _patch(
        "@@ -1,2 +1,2 @@",
        " def f():",
        "     pass",
    )
    # Header points at line 1: both occurrences (lines 100 and 200) sit far
    # outside the search window, and the full-file scan finds two identical
    # bodies, so the applier must refuse rather than guess.
    with pytest.raises(ValueError, match="hunk_context_mismatch"):
        apply_unified_diff(content, patch)
