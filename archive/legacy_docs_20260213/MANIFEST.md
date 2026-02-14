# Legacy Docs Archive Manifest (2026-02-13)

Purpose: archive experimental/legacy markdown artifacts without deleting them.

## Source to Archive Mapping

- `root/*.md`:
  - `CompleteArchitecturePlan_Refined.md`
  - `COMPREHENSIVE_REVIEW.md`
  - `graph_cache_beam.md`
  - `latency_breakdown.md`
  - `latency_debug_beam_cache.md`
  - `PHASE_5_SUMMARY.md`
  - `post_merge_60.md`

- `r2/*.md`:
  - `diagnostic_stack_integration_verification_report.md`
  - `diagnostic_telemetry_path_and_flags.md`
  - `problem_1_intent_gated_sufficiency_layer_architectural_plan.md`
  - `problem_1_verification_and_evaluation.md`
  - `problem_2_action_remediation_layer_specification.md`
  - `problem_2_verification.md`
  - `problem_3_cross_run_instability_detection_frozen_design_spec.md`
  - `problem_3_verification.md`
  - `problem_4_structural_explanation_gap_detection_frozen_design.md`
  - `problem_4_verification.md`

- `files/*.md`:
  - `00_ARCHITECTURE_OVERVIEW.md`
  - `01_INDEXING_PHASE.md`
  - `02_RETRIEVAL_PHASE.md`
  - `03_IMPLEMENTATION_ROADMAP.md`
  - `04_PERFORMANCE_OPTIMIZATIONS.md`
  - `README.md`

## Archive Location

`archive/legacy_docs_20260213/`

## Reversal Procedure

1. Move required file(s) from `archive/legacy_docs_20260213/<group>/` back to their original location.
2. Keep this manifest with the moved files for auditability.
3. Do not restore archived docs into active evaluation or runtime paths unless explicitly required.
