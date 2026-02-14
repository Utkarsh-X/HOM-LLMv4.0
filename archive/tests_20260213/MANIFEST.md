# Test Archive Manifest (2026-02-13)

Purpose: archive stale unit tests tied to archived alignment internals.

## Archived Tests

- `tests/unit/test_alignment.py` -> `archive/tests_20260213/unit/test_alignment.py`
- `tests/unit/test_alignment_classifier.py` -> `archive/tests_20260213/unit/test_alignment_classifier.py`
- `tests/unit/test_alignment_policy.py` -> `archive/tests_20260213/unit/test_alignment_policy.py`

## Rationale

These tests target alignment analyzer/classifier/policy internals that are no longer active in runtime and were archived in `archive/unused_python_20260213/`.

## Reversal

Move any test file back to `tests/unit/` if reactivating that subsystem.
