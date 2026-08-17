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
