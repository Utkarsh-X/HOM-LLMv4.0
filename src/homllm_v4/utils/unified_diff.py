"""Tolerant unified-diff application for in-memory file content.

Used by the canned (fake) edit provider to apply SWE-bench gold patches
deterministically, so the external suite can be regression-tested headlessly
without a live model.

The applier is deliberately lenient about hunk *counts*: real SWE-bench
patches (and other git-generated diffs) sometimes carry slightly wrong
``@@ -a,b +c,d @@`` line counts (the SWE-bench dataset is known for this).
Like ``git apply --recount``, we trust the hunk *body* and the hunk *start
line* and recompute everything else from the body.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _split_patch_lines(patch: str) -> list[str]:
    """Normalize a patch to LF and split into lines, dropping trailing blanks."""
    lines = patch.replace("\r\n", "\n").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _parse_hunks(patch_lines: Sequence[str]) -> list[tuple[int, list[str], list[str]]]:
    """Parse ``@@ -a,b +c,d @@`` hunks into (old_start, old_body, new_body)."""
    hunks: list[tuple[int, list[str], list[str]]] = []
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            match = _HUNK_HEADER_RE.match(line)
            if not match:
                raise ValueError(f"malformed_hunk_header: {line[:80]!r}")
            old_start = int(match.group(1))
            i += 1
            old_body: list[str] = []
            new_body: list[str] = []
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                body_line = patch_lines[i]
                if body_line.startswith("\\"):
                    # "\ No newline at end of file" marker — tolerated, ignored.
                    i += 1
                    continue
                if body_line.startswith(" "):
                    old_body.append(body_line[1:])
                    new_body.append(body_line[1:])
                elif body_line.startswith("-"):
                    old_body.append(body_line[1:])
                elif body_line.startswith("+"):
                    new_body.append(body_line[1:])
                else:
                    raise ValueError(f"unexpected_patch_line: {body_line[:80]!r}")
                i += 1
            hunks.append((old_start, old_body, new_body))
        else:
            # File headers (diff --git / --- / +++ / index) are metadata only.
            i += 1
    return hunks


def _find_hunk_position(
    lines: Sequence[str],
    old_start: int,
    old_body: Sequence[str],
    *,
    search_window: int = 60,
) -> int | None:
    """Locate the hunk body in ``lines``, anchored on the header start line.

    ``old_start`` is 1-based (a 0 start means insertion before line 1). The
    body is matched exactly at the expected position first; if that fails
    (wrong header counts or trimmed context), the body is searched within a
    window around it. The default window tolerates the line-number drift
    small models produce when they count hunks by hand. When even the window
    misses (models counting lines in a multi-thousand-line file can drift by
    hundreds), fall back to a full-file exact-body scan and apply only when
    the body is unambiguous -- line numbers become advisory, the body is
    authoritative, and ambiguity fails loudly instead of corrupting.
    """
    if not old_body:
        # Pure insertion: position is the header start (0 = before line 1).
        return max(0, old_start - 1)
    expected = max(0, old_start - 1)
    if lines[expected : expected + len(old_body)] == list(old_body):
        return expected
    lo = max(0, expected - search_window)
    hi = min(len(lines) - len(old_body) + 1, expected + len(old_body) + search_window)
    for pos in range(lo, hi):
        if lines[pos : pos + len(old_body)] == list(old_body):
            return pos
    full_matches = [
        pos
        for pos in range(0, len(lines) - len(old_body) + 1)
        if lines[pos : pos + len(old_body)] == list(old_body)
    ]
    if len(full_matches) == 1:
        return full_matches[0]
    return None


def apply_unified_diff(content: str, patch: str) -> str:
    """Apply a unified diff to ``content`` and return the new content.

    Line endings are normalized: ``content`` may be CRLF or LF and ``patch``
    may be CRLF or LF; the result is LF. Multiple hunks are applied
    bottom-up so earlier hunks never shift later positions.

    Raises ``ValueError`` with a descriptive message when the patch is
    malformed or a hunk's context does not match the content (so a
    fixture/provider mismatch fails loudly instead of silently corrupting).
    """
    lines: list[str] = content.splitlines()
    had_trailing_newline = content.endswith("\n") or content.endswith("\r")
    hunks = _parse_hunks(_split_patch_lines(patch))
    if not hunks:
        raise ValueError("no_hunks_found_in_patch")
    for old_start, old_body, new_body in reversed(hunks):
        pos = _find_hunk_position(lines, old_start, old_body)
        if pos is None:
            raise ValueError(f"hunk_context_mismatch_at_line: {old_start}")
        lines[pos : pos + len(old_body)] = new_body
    result = "\n".join(lines)
    # Preserve a trailing newline the input had (files that ended with one
    # should keep ending with one, so diffs stay noise-free).
    if had_trailing_newline and not result.endswith("\n"):
        result += "\n"
    return result


def unified_diff(
    before: str,
    after: str,
    *,
    fromfile: str = "a/file",
    tofile: str = "b/file",
) -> str:
    """Small convenience wrapper around :func:`difflib.unified_diff`.

    Produces a normalized LF diff, useful for comparing gold-patch results.
    """
    import difflib

    return "".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
