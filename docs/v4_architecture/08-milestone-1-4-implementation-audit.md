# v4 Milestone 1-4 Implementation Audit

Date: 2026-05-16

## Scope

This audit checks the current v4 implementation against the written Milestone 1-4 exit criteria in `06-migration-and-validation-plan.md`.

It does not claim product readiness. It only records whether the current implementation is strong enough to serve as a validated v4 foundation before broader Milestone 5 expansion.

## Verification Evidence

Commands run:

- `.\.venv\Scripts\python.exe -m pytest tests\unit -q`
  - Result: `629 passed, 7 skipped`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q`
  - Result: `177 passed, 6 skipped`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q`
  - Result: `181 passed, 6 skipped`; includes the expanded real-index provider suite, structured runner diagnostics, and workspace copy cache-artifact regressions.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q`
  - Result: `24 passed`; includes explicit quality-dimension metrics for real-index provider evaluations.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q`
  - Result: `23 passed`; includes target-known and target-unavailable direct-provider baseline controls.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q`
  - Result: `21 passed`; includes hard evidence-value target-selection cases for cache namespace invalidation and labelled metrics export.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_direct_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `19 passed`; includes direct-provider baseline planner, suite-level `planner_context_mode="direct_provider"`, and CLI propagation for `--planner-context-mode direct-provider`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `41 passed`; includes reusable provider write-verify runner repair orchestration, provider prompt hardening, fenced-JSON parsing, output-budget propagation, actual-invocation token metrics, real-index prompt preflight, provider trailing-newline preservation, job-queue non-reentrant-lock acceptance criteria, provider repair context, suite-level bounded provider repair, CLI repair-attempt propagation, and provider invocation failure classification.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `6 passed`; includes CLI regression coverage for real-index prompt preflight
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_v3_provider_patch_factory.py tests\unit\v4\test_provider_edit_proposer.py -q`
  - Result: `19 passed`; includes regression coverage that `--max-prompt-chars` propagates from CLI to the real-index suite and that the v3 provider patch factory applies the prompt cap before provider invocation
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q`
  - Result: `18 passed`; includes regression coverage that provider prompts include evidence context, provider patch planning passes retrieved target-file evidence content into the provider prompt, evidence context is constrained by per-item and total prompt budgets, prompt/evidence-context metrics propagate through planner telemetry, and oversized prompts fail before provider invocation
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call -q`
  - Result: `1 passed`; verifies suite-level prompt cap failure reports `provider_prompt_budget_exceeded` before patching or verification
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `5 passed`; includes regression coverage for expanded real-index provider patch cases and prompt-limit failure handling
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_command_service.py -q`
  - Result: `8 passed`; includes regression coverage that subprocesses do not inherit unlisted environment variables and do receive explicitly allowlisted variables
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_live_provider_edit_smoke.py -q`
  - Result: `2 skipped`
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py`
  - Result: passed
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_adapter_boundaries.py -q`
  - Result: `2 passed`
- manual forbidden import scan outside `adapters/`
  - Result: no v3 imports found
- `$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_retrieval_backed_patch_planner_smoke -q -s`
  - Result: `2 passed`
- `$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_retrieval_backed_patch_planner_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_planner_smoke -q -s`
  - Result: `3 passed`
- `$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_retrieval_backed_patch_planner_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_planner_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_execution_smoke -q -s`
  - Result: `4 passed`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_patch_work_provider --artifact-root temp\v4_fixture_patch_runs_provider --run-id provider-proposer-check`
  - Result: `4 passed_cases`, `0 failed_cases`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_patch_work_provider_adapter --artifact-root temp\v4_fixture_patch_runs_provider_adapter --run-id provider-adapter-check`
  - Result: `4 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_patch_work_provider_planner --artifact-root temp\v4_fixture_patch_runs_provider_planner --run-id provider-planner-check`
  - Result: `4 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work --artifact-root temp\v4_fixture_provider_patch_runs --run-id provider-fixture-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work2 --artifact-root temp\v4_fixture_provider_patch_runs2 --run-id provider-fixture-check-2`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_rollback --artifact-root temp\v4_fixture_provider_patch_runs_rollback --run-id provider-fixture-rollback-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_approval --artifact-root temp\v4_fixture_provider_patch_runs_approval --run-id provider-fixture-approval-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_approval_scope --artifact-root temp\v4_fixture_provider_patch_runs_approval_scope --run-id provider-fixture-approval-scope-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_approval_store --artifact-root temp\v4_fixture_provider_patch_runs_approval_store --run-id provider-fixture-approval-store-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_real_index --artifact-root temp\v4_fixture_provider_patch_runs_real_index --run-id provider-fixture-real-index-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_real_index_exec --artifact-root temp\v4_fixture_provider_patch_runs_real_index_exec --run-id provider-fixture-real-index-exec-check`
  - Result: `2 passed_cases`, `0 failed_cases`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work --artifact-root temp\v4_real_index_provider_patch_runs --run-id real-index-provider-patch-check --smoke-safe`
  - Result: `3 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 3}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_semantic --artifact-root temp\v4_real_index_provider_patch_runs_semantic --run-id real-index-provider-patch-semantic-check --smoke-safe`
  - Result: `4 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 4}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_semantic_3 --artifact-root temp\v4_real_index_provider_patch_runs_semantic_3 --run-id real-index-provider-patch-semantic-3-check --smoke-safe`
  - Result: `6 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 6}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_mode --artifact-root temp\v4_real_index_provider_patch_runs_live_mode --run-id real-index-provider-patch-live-mode-fake-check --smoke-safe`
  - Result: `6 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 6}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `5 passed`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_baseline --artifact-root temp\v4_real_index_provider_patch_runs_baseline --run-id real-index-provider-patch-baseline-check --smoke-safe`
  - Result: `6 passed_cases`, `0 failed_cases`, `baseline_case_count=3`, `stop_reason_counts={"verified": 6}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_artifacts --artifact-root temp\v4_real_index_provider_patch_runs_artifacts --run-id real-index-provider-patch-artifacts-check --smoke-safe`
  - Result: `6 passed_cases`, `0 failed_cases`, `baseline_case_count=3`, provider prompt/response artifacts were present for `string-truncate-guard`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py -q`
  - Result: `3 passed`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py tests\unit\v4\test_provider_patch_planner.py -q`
  - Result: `8 passed`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `9 passed`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_target_selection --artifact-root temp\v4_real_index_provider_patch_runs_target_selection --run-id real-index-provider-patch-target-selection-check --case-id string-truncate-guard-target-selection --smoke-safe`
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_target_metrics --artifact-root temp\v4_real_index_provider_patch_runs_target_metrics --run-id real-index-provider-patch-target-metrics-check --case-id string-truncate-guard-target-selection --smoke-safe`
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`; persisted `evaluation/summary.json` recorded `target_selection_decision=selected`, `resolved_target_file=utils/string_tools.py`, and `candidate_file_score_count=27`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_categorical_metrics --artifact-root temp\v4_real_index_provider_patch_runs_categorical_metrics --run-id real-index-provider-patch-categorical-metrics-check --case-id string-truncate-guard-target-selection --smoke-safe`
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`; top-level summary included `categorical_metric_counts={"target_selection_decision":{"selected":1},"resolved_target_file":{"utils/string_tools.py":1}}`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_file_path_target_selection_2 --artifact-root temp\v4_real_index_provider_patch_runs_file_path_target_selection_2 --run-id real-index-provider-patch-file-path-target-selection-check-2 --case-id validate-file-path-drive-guard-target-selection --smoke-safe`
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `target_selection_decision.selected=1`, `resolved_target_file=utils/validators.py`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_email_target_selection_2 --artifact-root temp\v4_real_index_provider_patch_runs_email_target_selection_2 --run-id real-index-provider-patch-email-target-selection-check-2 --case-id validate-email-local-dot-guard-target-selection --smoke-safe`
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `target_selection_decision.selected=1`, `resolved_target_file=utils/validators.py`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_target_selection_expanded --artifact-root temp\v4_real_index_provider_patch_runs_target_selection_expanded --run-id real-index-provider-patch-target-selection-expanded-check --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_write_verify_loop.py -q`
  - Result: `12 passed`; includes `verification_side_effect` regression coverage plus cleanup coverage for created and modified side-effect files when rollback is enabled
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_side_effect_guard --artifact-root temp\v4_real_index_provider_patch_runs_side_effect_guard --run-id real-index-provider-patch-side-effect-guard-check --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `stop_reason_counts={"verified":9}`; verification cache artifacts were ignored correctly
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_side_effect_cleanup --artifact-root temp\v4_real_index_provider_patch_runs_side_effect_cleanup --run-id real-index-provider-patch-side-effect-cleanup-check --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `stop_reason_counts={"verified":9}`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_env_filter --artifact-root temp\v4_real_index_provider_patch_runs_env_filter --run-id real-index-provider-patch-env-filter-check --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_evidence_context --artifact-root temp\v4_real_index_provider_patch_runs_evidence_context --run-id real-index-provider-patch-evidence-context-check --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_evidence_budget --artifact-root temp\v4_real_index_provider_patch_runs_evidence_budget --run-id real-index-provider-patch-evidence-budget-check --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_telemetry_2 --artifact-root temp\v4_real_index_provider_patch_runs_prompt_telemetry_2 --run-id real-index-provider-patch-prompt-telemetry-check-2 --smoke-safe`
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `prompt_char_count total=82765 average=9196.1`, `evidence_context_rendered_char_count total=29404 average=3267.1`, `evidence_context_truncated={"False":8,"True":1}`, `stop_reason_counts={"verified":9}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `5 passed`; includes regression coverage for the expanded real-index provider patch suite, verifies the added semantic cases mutate copied workspaces correctly, and verifies prompt-limit failure handling
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_more_behavior --artifact-root temp\v4_real_index_provider_patch_runs_more_behavior --run-id real-index-provider-patch-more-behavior-check --smoke-safe`
  - Result: `11 passed_cases`, `0 failed_cases`, `baseline_case_count=8`, `resolved_target_file` covers `api/routes.py`, `async_jobs/job_queue.py`, `cache/cache_manager.py`, `monitoring/metrics.py`, `utils/date_helpers.py`, `utils/string_tools.py`, and `utils/validators.py`, `prompt_char_count total=105599 average=9599.9`, `evidence_context_truncated={"False":10,"True":1}`, `stop_reason_counts={"verified":11}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_more_target_selection --artifact-root temp\v4_real_index_provider_patch_runs_more_target_selection --run-id real-index-provider-patch-more-target-selection-check --smoke-safe`
  - Result: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `resolved_target_file` covers `api/routes.py`, `async_jobs/job_queue.py`, `cache/cache_manager.py`, `monitoring/metrics.py`, `utils/date_helpers.py`, `utils/string_tools.py`, and `utils/validators.py`, `prompt_char_count total=128467 average=9882.1`, `evidence_context_truncated={"False":12,"True":1}`, `stop_reason_counts={"verified":13}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_size_gate --artifact-root temp\v4_real_index_provider_patch_runs_prompt_size_gate --run-id real-index-provider-patch-prompt-size-gate-check --smoke-safe`
  - Result: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `prompt_char_count total=128467 average=9882.1`, `evidence_context_truncated={"False":12,"True":1}`, `stop_reason_counts={"verified":13}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_limit_cli --artifact-root temp\v4_real_index_provider_patch_runs_prompt_limit_cli --run-id real-index-provider-patch-prompt-limit-cli-check --smoke-safe`
  - Result: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `prompt_char_count total=128467 average=9882.1`, `evidence_context_truncated={"False":12,"True":1}`, `stop_reason_counts={"verified":13}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_limit_failure --artifact-root temp\v4_real_index_provider_patch_runs_prompt_limit_failure --run-id real-index-provider-patch-prompt-limit-failure-check --case-id admin-routes-noop --max-prompt-chars 10 --smoke-safe`
  - Result: expected exit code `1`; JSON reported `1 failed_cases`, `0 passed_cases`, `stop_reason_counts={"patch_failed":1}`, and `error_code_counts={"provider_prompt_budget_exceeded":1}`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_limit_failure_tokens --artifact-root temp\v4_real_index_provider_patch_runs_prompt_limit_failure_tokens --run-id real-index-provider-patch-prompt-limit-failure-token-check --case-id admin-routes-noop --max-prompt-chars 10 --smoke-safe`
  - Result: expected exit code `1`; JSON reported `provider_prompt_budget_exceeded`, `provider_tokens_in=0.0`, and `provider_tokens_out=0.0`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --prompt-preflight --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_preflight --artifact-root temp\v4_real_index_provider_patch_runs_prompt_preflight --run-id real-index-provider-patch-prompt-preflight-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --case-id admin-routes-noop --smoke-safe`
  - Result: exit code `0`; JSON reported `preflight_only=true`, `requested_edit_provider_mode=live`, `live_api_key_present=false`, `prompt_char_count=9217.0`, `provider_tokens_in=0.0`, and `provider_tokens_out=0.0`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_single_json_contract --artifact-root temp\v4_real_index_provider_patch_runs_live_single_json_contract --run-id real-index-provider-patch-live-single-json-contract-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id admin-routes-noop --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified":1}`, `prompt_char_count=9563.0`, `provider_tokens_in=2526.0`, `provider_tokens_out=1410.0`, and `verification_count=1.0`; a no-index diff against the source file produced no output.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_string_truncate --artifact-root temp\v4_real_index_provider_patch_runs_live_string_truncate --run-id real-index-provider-patch-live-string-truncate-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard --max-prompt-chars 15000 --smoke-safe`
  - Result: expected failure; JSON reported `provider_response_truncated` and `Gemini finish_reason: max_tokens`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_string_truncate_31_lite --artifact-root temp\v4_real_index_provider_patch_runs_live_string_truncate_31_lite --run-id real-index-provider-patch-live-string-truncate-31-lite-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `1`; provider returned valid JSON and a patch, but verification failed because the generic `max(0, max_length - len(suffix))` fix did not satisfy `truncate_string('abcdef', 2) == 'ab'`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_string_truncate_quotes --artifact-root temp\v4_real_index_provider_patch_runs_live_string_truncate_quotes --run-id real-index-provider-patch-live-string-truncate-quotes-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=2023.0`, `provider_tokens_out=1370.0`, and `verification_count=1.0`; persisted patch added `if max_length <= len(suffix): return text[:max_length]`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_file_path_preview --artifact-root temp\v4_real_index_provider_patch_runs_live_file_path_preview --run-id real-index-provider-patch-live-file-path-preview-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id validate-file-path-drive-guard --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=2471.0`, `provider_tokens_out=1442.0`, and `verification_count=1.0`; persisted patch added Windows drive-qualified and backslash absolute-path rejection.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_email_preview --artifact-root temp\v4_real_index_provider_patch_runs_live_email_preview --run-id real-index-provider-patch-live-email-preview-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id validate-email-local-dot-guard --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=2053.0`, `provider_tokens_out=1432.0`, and `verification_count=1.0`; persisted patch added consecutive-local-dot rejection while preserving valid dotted local parts.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_string_truncate_target --artifact-root temp\v4_real_index_provider_patch_runs_live_string_truncate_target --run-id real-index-provider-patch-live-string-truncate-target-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard-target-selection --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"utils/string_tools.py":1}`, `baseline_case_count=1`, and `stop_reason_counts={"verified":1}`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_file_path_target --artifact-root temp\v4_real_index_provider_patch_runs_live_file_path_target --run-id real-index-provider-patch-live-file-path-target-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id validate-file-path-drive-guard-target-selection --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"utils/validators.py":1}`, `baseline_case_count=1`, and `stop_reason_counts={"verified":1}`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_email_target --artifact-root temp\v4_real_index_provider_patch_runs_live_email_target --run-id real-index-provider-patch-live-email-target-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id validate-email-local-dot-guard-target-selection --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"utils/validators.py":1}`, `baseline_case_count=1`, and `stop_reason_counts={"verified":1}`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_target_multicase --artifact-root temp\v4_real_index_provider_patch_runs_live_target_multicase --run-id real-index-provider-patch-live-target-multicase-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard-target-selection --case-id validate-file-path-drive-guard-target-selection --case-id validate-email-local-dot-guard-target-selection --max-prompt-chars 15000 --smoke-safe`
  - Result: exit code `0`; JSON reported `3 passed_cases`, `0 failed_cases`, `baseline_case_count=3`, `target_selection_decision={"selected":3}`, `resolved_target_file={"utils/string_tools.py":1,"utils/validators.py":2}`, `stop_reason_counts={"verified":3}`, `provider_tokens_in=8951.0`, `provider_tokens_out=4220.0`, and `prompt_char_count=29223.0`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_target_expanded --artifact-root temp\v4_real_index_provider_patch_runs_live_target_expanded --run-id real-index-provider-patch-live-target-expanded-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id parse-date-strip-target-selection --case-id job-queue-total-size-guard-target-selection --max-prompt-chars 15000 --smoke-safe`
  - Result: expected mixed result; JSON reported `1 passed_cases`, `1 failed_cases`, `error_code_counts={"provider_prompt_budget_exceeded":1}` because the job-queue prompt assembled to `17527` characters and exceeded the `15000` live cap before provider invocation.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_job_queue_cap22000 --artifact-root temp\v4_real_index_provider_patch_runs_live_job_queue_cap22000 --run-id real-index-provider-patch-live-job-queue-cap22000-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id job-queue-total-size-guard-target-selection --max-prompt-chars 22000 --smoke-safe`
  - Result: expected failure after provider invocation; JSON reported `verification_timeout`. The generated patch called `self.get_queue_size()` inside `with self._lock:`, which re-acquired the same non-reentrant lock.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_job_queue_expected_behavior --artifact-root temp\v4_real_index_provider_patch_runs_live_job_queue_expected_behavior --run-id real-index-provider-patch-live-job-queue-expected-behavior-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id job-queue-total-size-guard-target-selection --max-prompt-chars 22000 --smoke-safe`
  - Result: exit code `0`; JSON reported `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"async_jobs/job_queue.py":1}`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=5435.0`, `provider_tokens_out=2863.0`, and `prompt_char_count=17671.0` after the expected behavior explicitly forbade calling `get_queue_size` from inside the existing lock.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_target_full5_cap22000 --artifact-root temp\v4_real_index_provider_patch_runs_live_target_full5_cap22000 --run-id real-index-provider-patch-live-target-full5-cap22000-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard-target-selection --case-id validate-file-path-drive-guard-target-selection --case-id validate-email-local-dot-guard-target-selection --case-id parse-date-strip-target-selection --case-id job-queue-total-size-guard-target-selection --max-prompt-chars 22000 --smoke-safe`
  - Result: exit code `0`; JSON reported `5 passed_cases`, `0 failed_cases`, `baseline_case_count=5`, `target_selection_decision={"selected":5}`, `resolved_target_file={"async_jobs/job_queue.py":1,"utils/date_helpers.py":1,"utils/string_tools.py":1,"utils/validators.py":2}`, `stop_reason_counts={"verified":5}`, `provider_tokens_in=16628.0`, `provider_tokens_out=7938.0`, and `prompt_char_count=54039.0`.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_target_selection_full --artifact-root temp\v4_real_index_provider_patch_runs_target_selection_full --run-id real-index-provider-patch-target-selection-full-check --smoke-safe`
  - Result: `7 passed_cases`, `0 failed_cases`, `baseline_case_count=4`, `stop_reason_counts={"verified": 7}`; emitted existing `ollama not available, LocalProvider disabled` warning
- `$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke -q -s`
  - Result: `1 passed`
- `.\.venv\Scripts\python.exe runtime\v4_cli.py read-only --config configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml --workspace-root test_repo --query "How does admin search work?" --run-id cli-smoke-2 --artifact-root temp/v4_cli_smoke_runs --max-passes 1 --smoke-safe`
  - Result: exited `0`, stop reason `sufficient`, artifact root emitted

Earlier broader-suite blocker resolved:

- `eval/run_regression_cluster_audit.py` was restored so `tests/unit/test_run_regression_cluster_audit.py` can collect and pass.
- Python AST fallback parsing was added for environments without `tree-sitter-language-pack`.
- low-value context suppression was implemented behind explicit config flags.

## Milestone 1: v4 Service Shell

Status: substantially satisfied.

Evidence:

- v4 package exists under `src/homllm_v4/`.
- v3 retrieval, ranking, context, and index access are wrapped under `src/homllm_v4/adapters/`.
- typed contracts exist under `src/homllm_v4/contracts/`.
- `CapabilityResult` invariants are enforced by contract code.
- `ServiceRegistry.get(name, expected_type)` enforces runtime type safety.
- artifact and event ledgers are implemented through `ArtifactManager` and `EventWriter`.
- boundary tests prove v3 imports are constrained to adapter code.
- real v3 smoke proves a read-only path can call v3-derived services through v4 contracts.

Remaining weakness:

- vector/BM25 behavior is smoke-tested through v3 adapter paths but not yet covered by a dedicated frozen fixture index with deterministic channel assertions.

## Milestone 2: Read-Only Agent Loop

Status: satisfied for a minimal bounded loop.

Evidence:

- `ReadOnlyMultipassLoop` records pass data, sufficiency decisions, stop reasons, claim support, and final response artifacts.
- `RepetitionGuard` blocks repeated evidence states.
- sufficiency logic is deterministic and bounded for early milestones.
- CLI/API runner can execute a real read-only smoke path and persist artifacts.
- evaluation runners can execute read-only runtime paths through the harness.

Remaining weakness:

- sufficiency is intentionally simple and deterministic. It is appropriate for M2 validation, but not yet strong enough for broad real-world repository tasks.
- no LLM-backed response generation is wired into v4 yet.

## Milestone 3: Verification-Only Execution

Status: satisfied for a local restricted backend.

Evidence:

- `LocalCommandService` accepts structured argv, enforces workspace cwd containment, executable allowlists, timeout caps, and captured stdout/stderr.
- `LocalCommandService` now runs subprocesses with a policy-filtered environment, preventing arbitrary parent-process environment variables from leaking into verification commands by default while allowing explicit env var allowlisting.
- denied commands and invalid cwd return structured `CapabilityResult` errors.
- approval-gated commands can return structured `requires_approval` errors without executing.
- `ApprovalRegistry` resolves approved `once`, `task`, and `session` scopes for approval-gated command execution.
- `ApprovalStore` persists approval request/decision pairs to append-only JSONL and can replay them into `ApprovalRegistry`.
- write-verify runtime treats verification failure and timeout as blocking stop reasons.

Remaining weakness:

- sandboxing is contract-level and local-process restricted, not OS-level isolation.
- command allowlist coverage is minimal by design.
- environment filtering reduces accidental secret/config leakage into child processes, but it is not a substitute for OS-level sandboxing or process isolation.
- approval support has runtime contract and append-only storage, but no interactive approval UI or multi-process approval locking exists.

## Milestone 4: Patch-Capable Workflow

Status: satisfied for small deterministic patch tasks.

Evidence:

- `WorkspacePatchService` applies workspace-scoped file patches only.
- stale context is blocked by expected content hash checks.
- patch dry-run returns diffs without writing.
- patch application records previous file state and supports explicit rollback through `PatchRollbackRequest`.
- diff inspection now blocks unexpected file targets through `allowed_file_paths`.
- diff inspection now blocks excessive file scope through `max_file_changes`.
- `WriteVerifyLoop` applies patches, runs focused verification, blocks failed verification, supports bounded repair patch attempts, and can roll back applied patch files when `rollback_on_failure=True`.
- `WriteVerifyLoop` now snapshots the workspace around verification and blocks success with `verification_side_effect` if verification creates, modifies, or deletes files outside the patch set, ignoring known cache/artifact paths.
- When `rollback_on_failure=True`, `WriteVerifyLoop` now uses the pre-verification snapshot to delete created side-effect files and restore modified/deleted side-effect files outside the patch set.

Remaining weakness:

- patch representation is whole-file replacement, not structured hunk application.
- rollback is limited to files changed through `WorkspacePatchService`; it does not reverse arbitrary side effects from verification commands.
- arbitrary verification-command side effects are detected and cleaned from local snapshots when rollback is enabled, but this remains a local best-effort safeguard rather than OS-level isolation.
- core `WriteVerifyLoop` still only accepts bounded supplied patch attempts; provider-generated repair is now orchestrated by reusable `ProviderWriteVerifyRunner`, not inside the deterministic write loop.

## Promotion Decision

M1-M4 are ready to serve as the current v4 foundation for controlled experiments.

Do not treat this as production-ready. The next correct step is not broad feature expansion by default. The next step should be a focused Milestone 5 plan that chooses one narrow task class and measures it through the existing evaluation harness.

Recommended Milestone 5 first task class:

- small verified Python patch tasks against a frozen fixture repository

Reason:

- it directly exercises the HOM-LLM thesis: retrieve evidence first, patch narrowly, verify deterministically, and measure token/runtime/stop reasons.

## Milestone 5 Initial Slice

Status: initial slice implemented.

Evidence:

- frozen fixture repository exists under `fixtures/v4/python_patch_repo/`
- `build_write_verify_request_from_case` translates fixture patch cases into typed write-verify requests
- evaluation harness supports expected structured error codes for safety cases
- evaluation harness records run-level stop reason counts, error code counts, numeric metric totals, and numeric metric averages
- evaluation cases can name a baseline runner and persist candidate-vs-baseline numeric deltas
- real-index semantic write cases now use a no-patch baseline runner to verify the unchanged copied workspace fails the behavior assertion while the candidate patch verifies
- fixture safety suite covers:
  - verified patch
  - stale-context block
  - unexpected-file block
  - repair-budget exhaustion
- `tests/unit/v4/test_patch_case_evaluation.py` validates the suite through `V4EvaluationHarness`
- `run_python_patch_fixture_suite` exposes the suite as a reusable API
- `runtime/v4_cli.py eval-fixture-patch ...` runs the suite outside unit tests and emits JSON summary metrics
- `EvidenceBackedPatchPlanner` now validates target evidence, fresh direct reads, and expected content hashes before creating patch requests
- the fixture suite now goes through the evidence-backed planner before write-verify execution
- `RetrievalBackedPatchPlanner` connects `EvidenceRetrievalService`, `DirectReadService`, and `EvidenceBackedPatchPlanner` into a bounded retrieval-to-patch planning bridge
- `EvidenceTargetFileSelector` provides a pure deterministic foundation for selecting a target file from an evidence set when one file clearly dominates and returning structured ambiguity otherwise
- `ProviderProposedPatchPlanner` can now omit `target_file`, retrieve broadly, select a clear target from evidence, and stop before direct read/provider calls when selection is ambiguous or empty
- provider-proposed planner success telemetry now records `target_selection_decision`, `resolved_target_file`, and selector scores for evidence-selected targets
- real-index benchmark case metrics now expose target-selection decision and resolved target file, making target-omitted and file-coverage visibility available from persisted evaluation summaries
- `V4EvaluationHarness` now aggregates string and boolean case metrics under `categorical_metric_counts`, making target-selection coverage visible in top-level CLI JSON
- `BoundedEditProposer` defines the first safe seam where an injected proposer may suggest `new_content` for a runtime-fixed single target file
- `ProviderBackedEditProposer` defines the first provider-backed seam where an injected provider returns constrained JSON that is parsed, evidence-scoped, file-scoped, and passed through bounded proposal validation
- provider-backed edit proposals now carry typed `EditProposalEvidenceContext` records, and provider prompts include retrieved target-file evidence content rather than only evidence IDs
- provider-backed evidence context is rendered under explicit per-item and total prompt budgets to preserve the token-efficiency thesis before live provider synthesis
- provider prompt telemetry now records prompt character count, evidence-context item count, rendered evidence-context characters, and truncation status; real-index evaluation summaries aggregate these metrics
- provider-backed edit proposal can now enforce an optional hard `max_prompt_chars` limit and return `provider_prompt_budget_exceeded` before provider invocation when the assembled prompt is too large
- the real-index provider patch CLI exposes this policy as `--max-prompt-chars`, and the v3 provider patch factory passes it into `ProviderBackedEditProposer`
- provider-backed edit proposal can persist prompt and raw response artifacts when constructed with an `ArtifactManager`

Remaining weakness:

- the retrieval-backed bridge now has an opt-in real indexed-repo smoke against `test_repo` and local `indexes/`
- it now has a fake-provider multi-case write benchmark against `test_repo` and local `indexes/`, including ten behavior-verified semantic non-no-op cases
- patch content is still supplied by the evaluation case; the planner validates evidence and constructs requests but does not synthesize edits
- provider-backed proposal is verified with fake providers only; no real LLM provider adapter or live patch synthesis is wired yet
- baseline comparison is populated for three semantic real-index fake-provider write cases only; no external/live baseline suite has been populated yet
- token-efficiency reporting uses deterministic local proxies for write tasks, not full LLM token accounting

## Milestone 6 Initial Slice

Status: initial seam implemented.

Evidence:

- `ProviderBackedEditProposer` is pure v4 code and imports no v3 provider internals.
- provider interaction is represented by `EditProposalProvider`, `ProviderEditProposalRequest`, and `ProviderEditProposalResponse`.
- `V3ProviderEditProposalAdapter` connects the v4 provider edit proposal protocol to v3 `ProviderConnector` under `src/homllm_v4/adapters/` only.
- `build_v3_provider_edit_adapter` creates Gemini/OpenAI-backed edit proposal adapters through the v3 provider boundary.
- `build_v3_provider_edit_adapter_from_params` lets runtime/evaluation code request live provider adapters through primitive values without importing v3 `ModelConfig` outside `adapters/`.
- `build_v3_provider_proposed_patch_planner` wires v3 retrieval components, direct read, and provider-backed edit proposal into `ProviderProposedPatchPlanner`.
- `ProviderProposedPatchPlanner` connects retrieval, direct read, provider proposal, and evidence-backed patch planning without applying patches or running commands.
- `run_python_provider_patch_fixture_suite` exercises a fake-provider proposal through retrieval, direct read, patch planning, patch application, and pytest verification.
- `runtime/v4_cli.py eval-fixture-provider-patch ...` runs the provider-proposed fixture suite outside unit tests.
- `tests/unit/v4/test_live_provider_edit_smoke.py` defines an opt-in live provider smoke gated by `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1`; normal verification skips it.
- `test_live_provider_patch_can_apply_and_verify_in_fixture_workspace` extends the opt-in live provider scaffold from JSON proposal validation to provider-synthesized patch planning, patch application, and pytest verification in a copied fixture workspace.
- `test_real_v3_provider_proposed_patch_planner_smoke` proves real indexed v3 retrieval can feed provider-proposed patch planning with a fake provider.
- `test_real_v3_provider_proposed_patch_execution_smoke` copies `test_repo` into a temp workspace, uses real v3 indexed retrieval plus a fake no-op provider, applies the generated patch request through `WriteVerifyLoop`, and verifies the copied target with `compileall`.
- `run_real_index_provider_patch_suite` and `runtime/v4_cli.py eval-real-index-provider-patch ...` run a fifteen-case fake-provider benchmark against copied `test_repo` workspaces with real v3 indexed retrieval and v4 patch/verification runtime, including seven target-omitted cases and twelve behavior-verified semantic cases.
- `eval-real-index-provider-patch` now supports `--edit-provider-mode live`, `--live-provider`, `--live-model`, `--live-api-key-env`, and `--case-id` so live synthesis can be opt-in and case-limited.
- live real-index benchmark mode now fails preflight with `live_provider_api_key_required` before provider construction if no explicit API key is resolved.
- real-index benchmark case filtering now fails preflight with `unknown_case_ids` instead of silently running zero or unintended cases.
- CLI preflight failures for the real-index benchmark now return structured JSON containing `command`, `error_code`, and `message` instead of surfacing a traceback.
- `eval-real-index-provider-patch --list-cases` exposes benchmark case IDs and target metadata without running retrieval, provider calls, workspace copying, patching, or verification.
- `string-truncate-guard` patches `utils/string_tools.py::truncate_string` and verifies behavior with a focused Python assertion, not only syntax.
- `string-truncate-guard-target-selection` omits `target_file` from provider-proposed planning, relies on real indexed retrieval plus deterministic target selection, then patches and verifies the same truncate behavior.
- `validate-file-path-drive-guard` patches `utils/validators.py::validate_file_path` and verifies Windows drive/root path rejection.
- `validate-file-path-drive-guard-target-selection` omits `target_file`, relies on real indexed retrieval plus query-aware deterministic target selection, then patches and verifies Windows drive/root path rejection.
- `validate-email-local-dot-guard` patches `utils/validators.py::validate_email` and verifies consecutive local-part dot rejection without breaking a valid dotted local part.
- `validate-email-local-dot-guard-target-selection` omits `target_file`, relies on real indexed retrieval plus query-aware deterministic target selection, then patches and verifies consecutive local-part dot rejection.
- provider output must be JSON containing `target_file`, `new_content`, `rationale`, `evidence_ids`, and `risk_flags`.
- invalid JSON and missing required fields return structured `provider_response_invalid` failures.
- provider proposals referencing evidence outside the runtime-fixed evidence set return `proposal_evidence_scope_denied`.
- provider proposals targeting files outside `allowed_file_paths` are rejected by the existing bounded proposal validator.
- provider token/model usage is carried into v4 capability telemetry.
- provider prompt and raw response artifacts can be persisted for artifact-manager-backed proposers, and the real-index provider patch benchmark now passes its run artifact manager into the default v3-backed planner factory.
- provider prompts now include typed evidence context populated from retrieved target-file candidates, making the pre-live provider seam evidence-informed rather than ID-only.
- provider evidence-context prompt rendering now has explicit per-item and total context budgets so retrieval context cannot grow unbounded.
- provider prompt metrics now propagate through provider-proposed patch planning into real-index benchmark summaries, making evidence prompt size and truncation measurable before live provider runs.
- provider prompt-size gating is available at the provider proposer boundary, but the default benchmark path leaves it unset so existing offline cases remain comparable.
- prompt-size gating is now configurable from the real-index provider patch CLI, making the cost/safety cap usable for future opt-in live provider runs.
- prompt-size gating is now covered by a suite-level failure regression: an intentionally tiny cap stops `eval-real-index-provider-patch` before patching or verification with structured `provider_prompt_budget_exceeded` summary metrics.
- provider token accounting now comes from actual planner telemetry rather than static provider object attributes, so prompt-cap denials report zero provider tokens.
- `eval-real-index-provider-patch --prompt-preflight` can now run real retrieval, target resolution, evidence-context assembly, prompt artifact writing, and prompt-size measurement without invoking a live provider; this gives a controlled readiness step before paid/networked synthesis.
- live provider smoke has now verified one no-op case, ten semantic retrieval/evidence patches, and all six retried target-known direct-provider semantic cases in copied workspaces using Gemini; the retrieval/evidence path exercised real indexed retrieval plus deterministic target selection before live patch synthesis, and failed intermediate live runs produced structured evidence for truncation, invalid JSON dialect, prompt-budget failure, provider invocation failure, verification timeout, and volatile workspace-copy failures.
- live provider output budget is configurable through `--live-max-output-tokens`.
- provider response parsing now accepts Markdown-fenced JSON while still rejecting invalid JSON dialects.
- provider prompt contract now requires complete full-file content, valid JSON string encoding, normal source text after JSON parsing, no-op content preservation, and exact expected-behavior examples as acceptance criteria.
- provider-proposed patch planning preserves the original trailing newline when the provider returns full-file content without it.
- provider proposal prompts now accept explicit `repair_context`, and the real-index provider suite can run bounded provider repair attempts after verification failure or timeout while aggregating provider token and prompt metrics across attempts.
- `ProviderWriteVerifyRunner` extracts provider-backed patch planning, deterministic write-verify execution, verification-failure/timeout repair retries, repair-context construction, and planner-metric aggregation into reusable runtime code; the real-index provider suite now calls this runner instead of owning repair orchestration directly.
- provider invocation failures before any response are now classified as retryable `provider_invocation_failed` instead of being conflated with invalid provider JSON, and the real-index provider suite deterministically surfaces this class in error-code summaries.
- live repair-enabled probes with `gemini-3.1-flash-lite` and `gemini-3.1-flash-lite-preview` both verified `string-truncate-guard` first-shot with `provider_repair_attempt_count=0.0`, confirming the repair-enabled live CLI path can run while leaving actual live repair behavior unexercised.
- the full current internal 13-case real-index provider patch suite passed with live `gemini-3.1-flash-lite-preview`: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, seven resolved target files, `stop_reason_counts={"verified":13}`, `provider_tokens_in=41601.0`, `provider_tokens_out=21908.0`, and `prompt_char_count=139236.0`; repair was enabled but not exercised because all first patches verified.
- direct-provider baseline mode now runs the same real-index provider patch suite with known target files and no retrieved evidence context; fake and live `gemini-3.1-flash-lite-preview` direct-provider 13-case runs both passed with `13 passed_cases`, `0 failed_cases`, `planner_context_mode={"direct_provider":13}`, `target_selection_decision={"direct_supplied":13}`, and live token totals `provider_tokens_in=22975.0`, `provider_tokens_out=20903.0`, `prompt_char_count=85053.0`.
- the real-index suite now includes two harder target-omitted evidence-value cases: `cache-namespace-invalidate-target-selection` resolves `cache/cache_manager.py`, and `metrics-labelled-stats-target-selection` resolves `monitoring/metrics.py`; a fake-provider real-index CLI smoke passed both with `2 passed_cases`, `target_selection_decision={"selected":2}`, `candidate_file_score_count=43`, and low aggregate target-selection confidence `0.5885`, making them more useful than path-explicit cases for future RAG-vs-baseline comparisons.
- the same two hard evidence-value cases also passed live with `gemini-3.1-flash-lite-preview` in retrieval/evidence mode and direct-provider mode. Retrieval mode selected both targets and used `provider_tokens_in=9474.0`, `provider_tokens_out=4946.0`, `prompt_char_count=32829.0`; target-known direct-provider mode used `provider_tokens_in=4917.0`, `provider_tokens_out=4875.0`, `prompt_char_count=18700.0`.
- direct-provider target knowledge is now explicit: `direct_provider_target_source="actual"` keeps target-known baseline behavior, while `direct_provider_target_source="planner"` fails target-omitted cases with structured `direct_provider_target_required`. A CLI smoke over the two hard target-omitted cases produced `0 passed_cases`, `2 failed_cases`, `error_code_counts={"direct_provider_target_required":2}`, and zero provider tokens, proving retrieval mode's localization work is no longer hidden by the direct baseline.
- real-index evaluation summaries now expose quality-dimension categorical metrics before interpretation: `quality_requires_localization`, `quality_verification_kind`, `quality_provider_mode`, `quality_verification_mode`, and `quality_baseline_target_knowledge`. A two-case CLI smoke reported one compile case, one behavior case, one localization-required case, one supplied-target case, and `quality_baseline_target_knowledge={"retrieval_localizes":2}`.
- the expanded 15-case fake-provider real-index suite passed with `15 passed_cases`, `0 failed_cases`, `baseline_case_count=12`, `target_selection_decision={"selected":7,"supplied":8}`, and the expected quality categories for three compile no-op cases plus twelve behavior cases.
- the expanded 15-case live retrieval/evidence suite with `gemini-3.1-flash-lite-preview` produced `14 passed_cases`, `1 failed_case`, `baseline_case_count=12`, `stop_reason_counts={"verified":14,"patch_failed":1}`, and `error_code_counts={"provider_invocation_failed":1}`. The failed case was a provider/server disconnect before patch verification, while the run still recorded `quality_baseline_target_knowledge={"retrieval_localizes":15}`, `quality_requires_localization={"False":8,"True":7}`, `quality_verification_kind={"behavior":12,"compile":3}`, `target_selection_decision={"selected":6,"supplied":8}`, `provider_tokens_in=48101.0`, `provider_tokens_out=25438.0`, `prompt_char_count=172065.0`, and `provider_repair_attempt_count=0.0`.
- the expanded direct-provider target-known live comparison now has split-artifact evidence for all fifteen cases: the initial full run verified nine supplied-target cases, then a six-case fresh retry after the workspace-copy fix verified the six target-selection cases. Combined direct-provider target-known evidence is `15/15 verified`, `baseline_case_count=12`, `planner_context_mode={"direct_provider":15}`, `target_selection_decision={"direct_supplied":15}`, `quality_baseline_target_knowledge={"target_known":15}`, `quality_requires_localization={"False":8,"True":7}`, `quality_verification_kind={"behavior":12,"compile":3}`, `provider_tokens_in=27892.0`, `provider_tokens_out=25778.0`, `prompt_char_count=103753.0`, and `provider_repair_attempt_count=0.0`.
- real-index evaluation workspace materialization now ignores Python bytecode cache artifacts during case and baseline copies. This fixed a Windows-specific `shutil.copytree` failure mode where volatile `__pycache__/*.pyc` files could disappear or exceed path limits while copying live evaluation workspaces.
- `tests/unit/v4/test_provider_edit_proposer.py` validates the seam with fake providers only.

Remaining weakness:

- live LLM patch synthesis has now verified most of the expanded internal 15-case retrieval/evidence suite and all fifteen target-known direct-provider cases across split artifacts, but it is still one repository, one language, and a hand-authored task set.
- larger-suite behavior beyond the current 15-case internal benchmark remains unproven.
- the target-known direct-provider baseline matched or exceeded the retrieval/evidence path on pass rate with fewer input tokens on this suite, so the current internal benchmark is not yet hard enough to demonstrate a token-efficiency advantage from evidence context.
- even the two newer hard evidence-value live cases do not yet show a token-efficiency win for evidence context when the baseline is given the target file; their value is mainly in target localization and future grounding comparisons.
- quality-first evaluation now needs to compare correctness, localization, grounding, verification, and safety before token cost; target-unavailable baselines are a step toward that.
- bounded provider repair is verified with fake-provider tests; later live repair-enabled probes reached verified patches but did not exercise repair because both models passed first-shot.
- no prompt-quality evaluation exists for edit proposals yet.
- target selection is implemented for clear single-file cases, but it is not yet a general multi-file localization/decomposition system.
- provider-proposed patch execution now has a real-index fake-provider multi-case benchmark with twelve semantic non-no-op cases, including seven target-omitted cases and additional coverage for `utils/date_helpers.py`, `async_jobs/job_queue.py`, `cache/cache_manager.py`, and `monitoring/metrics.py`, but broader external indexed write coverage is still missing.
