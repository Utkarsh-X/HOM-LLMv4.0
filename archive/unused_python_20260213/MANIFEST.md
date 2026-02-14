# Unused Python Archive Manifest (2026-02-13)

Purpose: archive low-risk, unreferenced Python files during stability-first cleanup.

## Archived Files

- `delmelater.py` -> `archive/unused_python_20260213/root/delmelater.py`
- `src/homllm/alignment/analyzer.py` -> `archive/unused_python_20260213/src_alignment/analyzer.py`
- `src/homllm/alignment/classifier.py` -> `archive/unused_python_20260213/src_alignment/classifier.py`
- `src/homllm/alignment/policy/policy_engine.py` -> `archive/unused_python_20260213/src_alignment/policy_engine.py`
- `src/homllm/alignment/policy/policy_types.py` -> `archive/unused_python_20260213/src_alignment/policy_types.py`

## Restored Due To Runtime Dependency

- `bootstrap.py` restored to repository root (required by `runtime/run_query.py` import).

## Explicitly Not Archived (live imports found)

- `runtime/logger.py`
- `runtime/token_attribution.py`

## Notes

- `setup.py` intentionally left in place for packaging/tool compatibility.
- This is archive-only; no runtime logic edits were made.

## Reversal

Move any archived file back to its original path if needed.
