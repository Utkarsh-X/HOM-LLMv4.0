# Active Goal Completion Audit

Date: 2026-05-20

## Objective Restatement

The active objective is to proceed autonomously and carefully toward completing HOM-LLM v4 as far as possible according to the agreed plans, without rushing, while preserving architecture discipline and rewriting plans where needed.

Concrete success criteria implied by the objective and prior roadmap:

1. Preserve the production-grade direction without pretending v4 is already product-ready.
2. Build beside v3 rather than corrupting v3.
3. Keep RAG/evidence-first behavior as the differentiator.
4. Add bounded planning, writing, execution, and verification only through typed contracts.
5. Use plans before implementation.
6. Validate with tests, smoke checks, and evaluation artifacts.
7. Continue until the planned reachable milestone is genuinely complete.
8. Treat answer/patch quality, grounding, verification success, safety, and maintainability as primary; token usage is a constraint and diagnostic, not the sole optimization target.

## Prompt-to-Artifact Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| Engineering governance exists | `ENGINEERING_CODEX.md`, `AI_ENGINEERING_RULES.md`, `ARCHITECTURE_BOUNDARIES.md`, `TDD_WORKFLOW.md`, `RULES.md`, governance skill files | Satisfied |
| v4 architecture is documented | `docs/v4_architecture/01` through `08` plus this audit | Satisfied |
| v4 is built beside v3 | package under `src/homllm_v4/` | Satisfied |
| v3 behavior is not rewritten into v4 internals | v3 access constrained through `src/homllm_v4/adapters/`; boundary scan has no non-adapter v3 imports | Satisfied |
| M1 service shell exists | v4 contracts, registry, artifact manager, ledger writer, service wrappers, v3 adapters | Satisfied |
| M2 read-only loop exists | `ReadOnlyMultipassLoop`, sufficiency, repetition guard, read-only CLI/API smoke | Satisfied for minimal loop |
| M3 verification-only execution exists | `LocalCommandService`, structured command requests/results, allowlist, cwd containment, timeout, approval-gate, and filtered-environment tests | Satisfied for local restricted backend |
| Command approval contract exists | `CommandPolicy.approval_required_executables` and `requires_approval` command error distinguish approval-gated commands from ordinary denials | Satisfied as contract scaffold only |
| Approval scope registry exists | `ApprovalRegistry`, `ApprovalRequest`, and `ApprovalDecision` support once/task/session approvals for command execution | Satisfied in-memory only |
| Persisted approval store exists | `ApprovalStore` appends approval request/decision pairs to JSONL and replays them into `ApprovalRegistry` | Satisfied for audit/replay only |
| M4 patch-capable workflow exists | `WorkspacePatchService`, `WriteVerifyLoop`, stale-context checks, diff/file-scope inspection, bounded repair attempts, verification side-effect detection | Satisfied for small deterministic patch tasks |
| Patch rollback exists | `WorkspacePatchService.rollback`, `PatchRollbackRequest`, and `WriteVerifyLoop.rollback_on_failure` restore files changed through patch service after failed verification | Satisfied for patch-service file changes only |
| M5 deterministic write evaluation exists | fixture patch suite, `V4EvaluationHarness`, `eval-fixture-patch` CLI | Satisfied for initial task class |
| Safety cases are measurable | stale context, unexpected file change, repair budget exhaustion, expected error-code matching | Satisfied |
| Measurement hooks exist | summary metrics, numeric totals/averages, baseline runner hook, CLI JSON output | Satisfied |
| Evidence-backed patch planning exists | `EvidenceBackedPatchPlanner`, `PatchPlan`, tests | Satisfied |
| Retrieval-backed patch planning exists | `RetrievalBackedPatchPlanner`, tests, opt-in real indexed-repo smoke | Satisfied for planning only |
| Deterministic target-file selection exists | `EvidenceTargetFileSelector` selects a clear target file from evidence scores or returns structured ambiguity/no-candidate decisions | Satisfied and wired into provider-proposed patch planning |
| Bounded edit proposal seam exists | `BoundedEditProposer`, `EditProposalRequest`, `EditProposalResult`, unit tests | Satisfied for injected proposer only |
| Provider-backed edit proposal seam exists | `ProviderBackedEditProposer`, injected provider protocol, fenced-JSON parsing, bounded validation, typed evidence context in prompts, explicit evidence prompt budgets, hard prompt-size gate exposed through CLI/factory, live output-token budget, suite-level prompt-cap failure regression, actual-invocation provider token metrics, no-provider-call prompt preflight, prompt/evidence telemetry, optional prompt/response artifact capture, fake-provider tests | Satisfied with fake-provider tests, bounded live Gemini smokes, expanded 15-case live evidence, and split-artifact target-known direct-provider comparison |
| v3 provider connector adapter exists | `V3ProviderEditProposalAdapter` translates v4 provider proposal requests to v3 `ProviderConnector` calls under `adapters/` only | Satisfied for fake v3 connector tests only |
| v3 provider adapter factory exists | `build_v3_provider_edit_adapter` constructs Gemini/OpenAI edit proposal adapters through the v3 provider boundary | Satisfied with injected fake provider tests |
| Provider-proposed patch planning exists | `ProviderProposedPatchPlanner` connects retrieval, direct read, provider proposal, and evidence-backed patch planning | Satisfied for fake provider/service tests only |
| Real-index provider-proposed planning smoke exists | `test_real_v3_provider_proposed_patch_planner_smoke` uses v3 indexed retrieval with fake provider proposal | Satisfied as opt-in planning smoke only |
| Real-index provider-proposed execution smoke exists | `test_real_v3_provider_proposed_patch_execution_smoke` copies `test_repo`, uses real v3 indexed retrieval plus fake no-op provider planning, then runs v4 patch apply and `compileall` verification | Satisfied as opt-in single-case execution smoke only |
| Real-index provider-proposed write benchmark exists | `run_real_index_provider_patch_suite` and `eval-real-index-provider-patch` run fifteen fake-provider cases against copied `test_repo` workspaces with real v3 indexed retrieval, v4 verification, provider prompt/response artifacts, no-patch baselines for twelve semantic cases, and seven target-omitted cases | Satisfied for three no-op cases plus twelve semantic non-no-op cases |
| Provider-proposed fixture execution exists | `run_python_provider_patch_fixture_suite` and `eval-fixture-provider-patch` run fake provider proposals through planning, patching, and verification | Satisfied for deterministic fake-provider fixtures only |
| Opt-in live provider smoke exists | `test_live_provider_edit_smoke.py` is gated by `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1` and skipped by default | Satisfied as scaffold only |
| Opt-in live provider patch execution smoke exists | `test_live_provider_patch_can_apply_and_verify_in_fixture_workspace` can run provider-synthesized fixture patch planning, application, and pytest verification when explicitly enabled | Satisfied as skipped-by-default scaffold only |
| Opt-in live provider real-index benchmark mode exists | `eval-real-index-provider-patch --edit-provider-mode live` supports live provider/model/key-env selection, `--list-cases`, validated `--case-id` filtering, missing-key preflight, structured JSON CLI errors, prompt caps, output-token caps, quality metrics, retrieval/evidence mode, and target-known direct-provider mode | Satisfied for the current internal 15-case benchmark, with one retrieval/evidence provider availability failure and split-artifact direct-provider evidence |
| Real-index provider benchmark suite profiles exist | `eval-real-index-provider-patch --case-suite` and suite-aware metadata can run the original `core` suite or the second `inventory` fixture suite | Satisfied for local fake-provider suites; live cross-repo evidence not yet run |
| MVP local coding-agent task command exists | `agent-task` CLI and `run_agent_task` API run one bounded provider-proposed edit task through planning, patching, verification, optional repair, rollback-on-failure, and artifacts | Satisfied as first local MVP slice with live Gemini smoke |
| Agent task can prepare/load a repo index | `agent-task --prepare-index` rewrites a template config to run-local index paths, builds the v3 index, passes the generated config into planning, and reports index paths/metrics | Satisfied for opt-in local CLI/API path; not yet a polished interactive session flow |
| First local session-like command exists | `agent-session` CLI and `run_agent_session` API can prepare a run-local repo index, run a grounded read-only ask, and optionally run one bounded edit/verify sub-task with shared generated config and artifacts | Satisfied as one-shot local session slice with live Gemini smoke; not an interactive REPL |
| Provider-grounded session answers exist | `GroundedAnswerSynthesizer` and `agent-session --answer-provider-mode live` synthesize a concise answer from retrieved `ContextPack` blocks, write provider prompt/response artifacts, expose token/prompt metrics, and fall back to the deterministic read-only summary on answer synthesis failure | Satisfied as opt-in live session-answer slice with Gemini smoke; not a broad Q&A benchmark |
| Persistent MVP session state exists | `AgentSessionStore` writes `<artifact_root>/<session_id>/session.json` with workspace/config/index metadata and append-only turn records; `run_agent_session` persists one turn by default and supports opt-out | Satisfied as state backbone only; no headless multi-step runner yet |
| Headless MVP agent command exists | `HomllmAgentRunRequest`, `run_homllm_agent`, and `homllm-agent run` wrap the session path, force session-state persistence, and write `<artifact_root>/<run_id>/trajectory.json` with repo-index, grounded-answer, bounded-edit, and verification steps | Satisfied as first headless product-shaped command; not yet a multi-turn autonomous loop |
| Internal homllm-agent benchmark runner exists | `run_homllm_agent_benchmark`, `INTERNAL_AGENT_BENCHMARK_CASES`, and `eval-homllm-agent` provide a 10-case internal suite that copies a workspace per case, invokes `homllm-agent run`, consumes `trajectory.json`, writes `evaluation/summary.json`, aggregates pass/fail, stop reasons, verification counts, token metrics, index metrics, and trajectory statuses, and rejects verified runs with incomplete/ungrounded trajectories | Satisfied for local fake/injected regression coverage and a live Gemini three-case slice; full 10-case live execution remains |
| Real v3/index smoke exists | `HOMLLM_V4_RUN_REAL_V3_SMOKE=1` tests pass for read-only loop, retrieval-backed planner, provider-proposed planner, and provider-proposed execution | Satisfied |
| v4 unit suite is green | `.\\.venv\\Scripts\\python.exe -m pytest tests\\unit\\v4 -q` -> `220 passed, 6 skipped` | Satisfied for the v4 scope; broader repository suite is not claimed here |
| Full product-grade coding agent exists | bounded live LLM patch synthesis results plus current internal 15-case live evidence, no external live baseline, no product UX | Not satisfied |

## Fresh Verification Evidence

Commands run in this checkpoint:

- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py::test_run_agent_task_applies_and_verifies_single_live_style_edit -q`
  - Result: failed first with `ModuleNotFoundError: No module named 'homllm_v4.runtime.agent_task'`, then passed after adding the MVP agent-task orchestration API.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_agent_task_with_live_defaults -q`
  - Result: failed first because `homllm_v4.cli` had no `run_agent_task`/`agent-task` path, then passed after adding CLI wiring with default `gemini-3.1-flash-lite-preview`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `13 passed`; verifies the first MVP local edit command/API surface plus existing provider fixture CLI behavior.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_preserves_windows_verification_command -q`
  - Result: failed first because POSIX `shlex.split()` mangled Windows backslash paths and split quote-heavy `python -c` verification commands incorrectly; passed after adding Windows-aware command splitting and quote cleanup.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `14 passed`; verifies the MVP local edit command/API surface, existing provider fixture CLI behavior, and Windows verification-command parsing.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py agent-task --config temp\v4_inventory_index_config_20260520a.yaml --workspace-root temp\v4_agent_task_live_inventory_workspace_20260520223205 --artifact-root temp\v4_agent_task_live_inventory_runs_20260520223448 --run-id agent-task-live-inventory-sku-20260520223448 --query "inventory items normalize_sku strip surrounding whitespace before uppercase" --intent "Make SKU normalization ignore surrounding whitespace before uppercasing." --expected-behavior "normalize_sku(' sku-1 ') returns 'SKU-1'." --target-file inventory/items.py --verification-cmd "<venv python> verify_sku.py" --live-api-key-env GOOGLE_API_KEY --live-model gemini-3.1-flash-lite-preview --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe`
  - Result: first sandboxed live attempt reached the provider path and failed with `provider_invocation_failed` / `WinError 10013`; rerun with network escalation returned exit code `0`, `stop_reason="verified"`, `patch_attempt_count=1`, `verification_count=1`, `provider_tokens_in=520`, `provider_tokens_out=159`, and `resolved_target_file="inventory/items.py"`. The copied workspace file changed to `return sku.strip().upper()`, and `events.jsonl` records `patch_completed`, `verification_completed` with exit code `0`, and `run_completed` with `rolled_back=false`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py::test_run_agent_task_can_prepare_run_local_index_config -q`
  - Result: failed first with `TypeError: AgentTaskRequest.__init__() got an unexpected keyword argument 'prepare_index'`, then passed after adding `runtime.agent_index` and API wiring.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_agent_task_with_index_prep_flags -q`
  - Result: failed first because `agent-task` did not accept `--prepare-index`, `--index-artifact-dir`, `--index-incremental`, or `--index-skip-vectors`; passed after CLI wiring and JSON output additions.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: initially exposed older CLI test doubles missing new index result fields; after backward-safe JSON emission, `16 passed`.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py agent-task --config configs\default.yaml --workspace-root temp\v4_agent_task_auto_index_live_workspace_20260521230054 --artifact-root temp\v4_agent_task_auto_index_live_runs_20260521230054 --run-id agent-task-auto-index-live-sku-20260521230054 --query "inventory items normalize_sku strip surrounding whitespace before uppercase" --intent "Make SKU normalization ignore surrounding whitespace before uppercasing." --expected-behavior "normalize_sku(' sku-2 ') returns 'SKU-2'." --target-file inventory/items.py --verification-cmd "<venv python> verify_sku.py" --live-api-key-env GOOGLE_API_KEY --live-model gemini-3.1-flash-lite-preview --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe --prepare-index --index-skip-vectors`
  - Result: exit code `0`, `index_built=true`, generated config under the run's `index/generated_config.yaml`, index metrics `source_file_count=7` and `symbol_count=3`, `stop_reason="verified"`, `patch_attempt_count=1`, `verification_count=1`, `provider_tokens_in=522`, `provider_tokens_out=175`, and `resolved_target_file="inventory/items.py"`. The copied workspace file changed to `return sku.strip().upper()`. Non-fatal v3 indexer warnings remain: tree-sitter parsing unavailable, `_PythonAstNode.parent` errors on package `__init__.py` files, and the temporary verification script was scanned and produced a BOM parse warning.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q`
  - Result: failed first because `homllm_v4.runtime.agent_session` did not exist; after adding the session orchestrator, index-prep handoff, and Windows-safe `-ask`/`-edit` sub-run IDs, passed with `3 passed`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_agent_session_prints_combined_json -q`
  - Result: failed first because `homllm_v4.cli` had no `agent-session` command; passed after adding CLI parsing, live-provider option propagation, optional edit verification enforcement, and combined JSON output.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `24 passed`; verifies the session API/CLI slice together with the existing local agent-task loop and provider fixture CLI behavior.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py agent-session --config configs\default.yaml --workspace-root temp\v4_agent_session_live_workspace_20260523013753 --artifact-root temp\v4_agent_session_live_runs_20260523013753 --run-id agent-session-live-sku-20260523013753 --query "inventory items normalize_sku implementation and behavior" --edit-intent "Make SKU normalization ignore surrounding whitespace before uppercasing." --expected-behavior "normalize_sku(' sku-4 ') returns 'SKU-4'." --target-file inventory/items.py --verification-cmd "<venv python> verify_sku.py" --live-api-key-env GOOGLE_API_KEY --live-model gemini-3.1-flash-lite-preview --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe --prepare-index --index-skip-vectors`
  - Result: first live attempt failed before provider invocation because colon-delimited sub-run IDs created invalid Windows artifact paths; after switching to `-ask` and `-edit`, rerun exited `0` with `index_built=true`, `ask_stop_reason="sufficient"`, `edit_stop_reason="verified"`, index metrics `source_file_count=7` and `symbol_count=3`, `patch_attempt_count=1`, `verification_count=1`, `provider_repair_attempt_count=0`, `provider_tokens_in=520`, `provider_tokens_out=171`, and `resolved_target_file="inventory/items.py"`. The copied workspace file changed to `return sku.strip().upper()`. Non-fatal indexer warnings remained: tree-sitter parsing unavailable, `_PythonAstNode.parent` errors on package `__init__.py` files, partial graph/callgraph topology warnings, and a BOM parse warning for the temporary verification script.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py::test_grounded_answer_synthesizer_uses_context_and_writes_artifacts -q`
  - Result: failed first with `ModuleNotFoundError: No module named 'homllm_v4.runtime.grounded_answer'`; passed after adding the session-edge grounded answer synthesizer. A later citation-format regression test failed until context blocks were rendered as `[file.py:start-end] evidence_id=...`, after which it passed.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py -q`
  - Result: `5 passed`; verifies provider prompt construction, prompt/response artifacts, token/model metrics, missing-context failure, prompt-budget failure before provider call, provider invocation failure, and blank-response failure.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py::test_run_agent_session_synthesizes_grounded_answer_from_context -q`
  - Result: failed first with `TypeError: AgentSessionRequest.__init__() got an unexpected keyword argument 'answer_provider_mode'`; passed after wiring answer synthesis into `run_agent_session`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q`
  - Result: `5 passed`; verifies ask-only summary mode, index prep, ask-then-edit, provider answer synthesis, and fallback to read-only summary without blocking edit execution.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_agent_session_prints_combined_json -q`
  - Result: failed first because `agent-session` did not accept `--answer-provider-mode`; passed after adding CLI request propagation and JSON fields for `answer_provider_mode`, `answer_error_code`, and `answer_metrics`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `31 passed`; verifies the grounded answer slice together with the session CLI/API, existing local agent-task loop, and provider fixture CLI behavior.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py agent-session --config configs\default.yaml --workspace-root temp\v4_grounded_answer_live_workspace_20260525000233 --artifact-root temp\v4_grounded_answer_live_runs_20260525000233 --run-id grounded-answer-live-citation-20260525000233 --query "Where is normalize_sku implemented, and what behavior does it currently have?" --answer-provider-mode live --live-api-key-env GOOGLE_API_KEY --live-model gemini-3.1-flash-lite-preview --live-max-output-tokens 2048 --max-prompt-chars 22000 --smoke-safe --prepare-index --index-skip-vectors`
  - Result: exit code `0`, `index_built=true`, `ask_stop_reason="sufficient"`, `answer_error_code=null`, `answer_provider_mode="live"`, `answer_text` identified `normalize_sku` in `inventory/items.py [inventory/items.py:1-2]` and described uppercase behavior, answer metrics `prompt_char_count=601`, `context_block_count=2`, `context_rendered_char_count=116`, `provider_tokens_in=185`, `provider_tokens_out=41`, `provider_model="gemini-3.1-flash-lite-preview"`, and `artifact_count=2`. Prompt and response artifacts were written under the ask run's `provider/` directory. Non-fatal v3 indexer warnings remained: tree-sitter parsing unavailable, `_PythonAstNode.parent` errors on package `__init__.py` files, partial graph/callgraph topology warnings, and submodular utility guard warnings.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_session_state.py::test_session_store_creates_loads_and_appends_turns -q`
  - Result: failed first with `ModuleNotFoundError: No module named 'homllm_v4.runtime.session_state'`; passed after adding `AgentSessionStore`, `AgentSessionState`, and `AgentSessionTurn`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_session_state.py -q`
  - Result: `3 passed`; verifies create/load/append behavior, path containment for session ids, and index metadata persistence.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py::test_run_agent_session_persists_session_turn_state -q`
  - Result: failed first because `session.json` was not written; after wiring `AgentSessionStore` into `run_agent_session`, passed with generated effective index config stored for later turn reuse.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q`
  - Result: `7 passed`; verifies existing session ask/edit/answer behavior plus default session-state persistence and explicit persistence opt-out.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_run.py::test_run_homllm_agent_writes_trajectory_and_session_state_path -q`
  - Result: failed first with `ModuleNotFoundError: No module named 'homllm_v4.runtime.agent_run'`, then passed after adding the headless wrapper and trajectory artifact writer.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_homllm_agent_run_prints_json_summary -q`
  - Result: failed first because `homllm_v4.cli` had no `run_homllm_agent`/`homllm-agent run` path, then passed after adding nested CLI parsing and JSON output.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_run.py tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py -q`
  - Result: `14 passed`; verifies the headless agent-run wrapper, persistent session handoff, existing session behavior, and CLI JSON contracts.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_benchmark.py::test_internal_agent_benchmark_suite_has_mvp_case_count -q`
  - Result: failed first with `ModuleNotFoundError: No module named 'homllm_v4.evaluation.agent_benchmark'`, then passed after adding the internal benchmark suite and runner module.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_benchmark.py -q`
  - Result: `2 passed`; verifies the 10-case internal suite contract and trajectory-based benchmark aggregation.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_eval_homllm_agent_lists_cases -q`
  - Result: failed first because `homllm_v4.cli` had no `agent_benchmark_case_metadata`/`eval-homllm-agent` path, then passed after adding CLI list mode.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_eval_homllm_agent_runs_benchmark -q`
  - Result: failed first because `homllm_v4.cli` had no `run_homllm_agent_benchmark`/`eval-homllm-agent` path, then passed after adding CLI run mode.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_benchmark.py tests\unit\v4\test_agent_run.py tests\unit\v4\test_cli_api.py -q`
  - Result: `11 passed`; verifies the benchmark runner, headless agent wrapper, and CLI JSON contracts.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `29 passed`; verifies suite-profile metadata, inventory fixture execution, CLI `--case-suite` propagation, and existing provider CLI behavior.
- `.\.venv\Scripts\python.exe runtime\index_repo.py --repo fixtures\v4\inventory_service_repo --config temp\v4_inventory_index_config_20260520a.yaml --skip-vectors --json --progress-interval 1`
  - Result: passed and built a temporary BM25/metadata index under `temp/v4_inventory_indexes_20260520a`; emitted existing local indexing warnings, including missing tree-sitter parsing and partial graph topology, so this is BM25/metadata evidence rather than graph-rich evidence.
- `.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config temp\v4_inventory_index_config_20260520a.yaml --source-workspace-root fixtures\v4\inventory_service_repo --workspace-root temp\v4_inventory_provider_patch_work_20260520b --artifact-root temp\v4_inventory_provider_patch_runs_20260520b --run-id inventory-provider-fake-smoke-20260520b --case-suite inventory --smoke-safe`
  - Result: `4 passed_cases`, `0 failed_cases`, `baseline_case_count=3`, `target_selection_decision={"selected":1,"supplied":3}`, resolved target files across `inventory/items.py`, `pricing/discounts.py`, and `orders/fulfillment.py`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q`
  - Result: `185 passed, 6 skipped`; includes cross-repo suite-profile coverage.
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q`
  - Result: `177 passed, 6 skipped`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q`
  - Result: `181 passed, 6 skipped`; includes expanded real-index provider coverage, structured runner diagnostics, and workspace copy cache-artifact regressions
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`
  - Result: passed
- `.\.venv\Scripts\python.exe -m pytest tests\unit -q`
  - Result: `629 passed, 7 skipped`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q`
  - Result: `24 passed`; verifies explicit quality-dimension metrics plus target-known/target-unavailable baseline controls
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q`
  - Result: `23 passed`; verifies target-known and target-unavailable direct-provider baseline controls, hard target-selection cases, CLI propagation, and direct-provider planner coverage
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q`
  - Result: `21 passed`; verifies the hard cache/metrics target-selection cases plus CLI and direct-provider baseline coverage
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_direct_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `19 passed`; verifies direct-provider baseline planner, suite mode, and CLI propagation
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `41 passed`; verifies reusable provider write-verify runner repair orchestration plus the provider planner/evaluation suite seams
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py -q`
  - Result: `6 passed`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_v3_provider_patch_factory.py tests\unit\v4\test_provider_edit_proposer.py -q`
  - Result: `19 passed`; verifies `--max-prompt-chars` CLI propagation and v3 provider patch factory enforcement before provider invocation
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q`
  - Result: `18 passed`; verifies provider prompt evidence-context rendering, planner handoff of retrieved target-file evidence content, per-item/total prompt-budget truncation, planner propagation of prompt metrics, and the hard prompt-size gate before provider invocation
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_command_service.py -q`
  - Result: `8 passed`; verifies structured command execution, allowlist/cwd/timeout behavior, approval-gated execution, default environment filtering, and explicit environment allowlisting
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call -q`
  - Result: `1 passed`; verifies an intentionally tiny prompt cap stops the provider-proposed real-index suite with `provider_prompt_budget_exceeded`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `5 passed`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py -q`
  - Result: `11 passed`; verifies provider token telemetry handoff and real-index suite prompt-cap failure metrics together
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_prompt_preflight_without_live_provider_call -q`
  - Result: `1 passed`; verifies `--prompt-preflight` uses fake provider mode plus zero prompt cap while reporting requested live-provider metadata
- `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_live_provider_edit_smoke.py -q`
  - Result: `2 skipped`
- `.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py`
  - Result: passed
- boundary scan for forbidden v3 imports outside adapters
  - Result: no output
- real v3 read-only smoke, retrieval-backed planner smoke, provider-proposed planner smoke, and provider-proposed execution smoke
  - Result: `4 passed`
- fixture patch CLI smoke
  - Result: `4 passed_cases`, `0 failed_cases`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- provider-proposed fixture CLI smoke
  - Result: `2 passed_cases`, `0 failed_cases`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- provider-proposed fixture CLI smoke with a fresh workspace/run id after an earlier reused-workspace run raised expected `case_workspace_exists` `ValueError`
  - Result: `2 passed_cases`, `0 failed_cases`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed write benchmark CLI smoke
  - Result: `3 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 3}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed semantic write benchmark CLI smoke
  - Result: `4 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 4}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed expanded semantic write benchmark CLI smoke
  - Result: `6 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 6}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed live-mode-compatible fake CLI smoke
  - Result: `6 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified": 6}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed semantic no-patch baseline CLI smoke
  - Result: `6 passed_cases`, `0 failed_cases`, `baseline_case_count=3`, `stop_reason_counts={"verified": 6}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed provider-artifact CLI smoke
  - Result: `6 passed_cases`, `0 failed_cases`, `baseline_case_count=3`; provider prompt/response artifacts were present for `string-truncate-guard`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- deterministic target-file selector unit test
  - Result: `3 passed`
- deterministic target-file selector plus provider-proposed planner target-selection tests
  - Result: `8 passed`
- provider-proposed planner target-selection telemetry plus real-index suite tests
  - Result: `9 passed`
- real-index provider-proposed target-omitted case CLI smoke
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed target-selection metrics CLI smoke
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`; persisted `evaluation/summary.json` recorded `target_selection_decision=selected`, `resolved_target_file=utils/string_tools.py`, and `candidate_file_score_count=27`
- real-index provider-proposed categorical summary metrics CLI smoke
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`; top-level summary included `categorical_metric_counts={"target_selection_decision":{"selected":1},"resolved_target_file":{"utils/string_tools.py":1}}`
- real-index provider-proposed seven-case CLI smoke
  - Result: `7 passed_cases`, `0 failed_cases`, `baseline_case_count=4`, `stop_reason_counts={"verified": 7}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- real-index provider-proposed validator target-selection diagnostics
  - Initial result: both new validator target-omitted cases stopped safely with `target_selection_ambiguous`; diagnostic retrieval showed score-only selection was too weak because `utils/validators.py` and nearby utility files had close scores.
- real-index provider-proposed file-path validator target-selection CLI smoke
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `target_selection_decision.selected=1`, `resolved_target_file=utils/validators.py`
- real-index provider-proposed email validator target-selection CLI smoke
  - Result: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `target_selection_decision.selected=1`, `resolved_target_file=utils/validators.py`
- real-index provider-proposed nine-case CLI smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`; latest run emitted existing `ollama not available, LocalProvider disabled` warning
- verification side-effect guard unit test
  - Result: `test_write_verify_loop.py` reports `10 passed`; unexpected `side_effect.txt` writes now stop with `verification_side_effect`
- real-index provider-proposed side-effect guard compatibility smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `stop_reason_counts={"verified":9}`; Python cache artifacts from verification were ignored correctly
- verification side-effect cleanup unit tests
  - Result: `test_write_verify_loop.py` reports `12 passed`; created side-effect files are deleted and modified unrelated files are restored when `rollback_on_failure=True`
- real-index provider-proposed side-effect cleanup compatibility smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `stop_reason_counts={"verified":9}`
- real-index provider-proposed command-environment-filter compatibility smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`
- real-index provider-proposed evidence-context compatibility smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`
- real-index provider-proposed evidence-prompt-budget compatibility smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `target_selection_decision={"selected":3,"supplied":6}`, `stop_reason_counts={"verified":9}`
- real-index provider-proposed prompt-telemetry compatibility smoke
  - Result: `9 passed_cases`, `0 failed_cases`, `baseline_case_count=6`, `prompt_char_count total=82765 average=9196.1`, `evidence_context_rendered_char_count total=29404 average=3267.1`, `evidence_context_truncated={"False":8,"True":1}`, `stop_reason_counts={"verified":9}`
- real-index provider-proposed expanded behavior benchmark smoke
  - Result: `11 passed_cases`, `0 failed_cases`, `baseline_case_count=8`, `resolved_target_file` covers `api/routes.py`, `async_jobs/job_queue.py`, `cache/cache_manager.py`, `monitoring/metrics.py`, `utils/date_helpers.py`, `utils/string_tools.py`, and `utils/validators.py`, `prompt_char_count total=105599 average=9599.9`, `evidence_context_truncated={"False":10,"True":1}`, `stop_reason_counts={"verified":11}`
- real-index provider-proposed expanded target-selection benchmark smoke
  - Result: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `resolved_target_file` covers `api/routes.py`, `async_jobs/job_queue.py`, `cache/cache_manager.py`, `monitoring/metrics.py`, `utils/date_helpers.py`, `utils/string_tools.py`, and `utils/validators.py`, `prompt_char_count total=128467 average=9882.1`, `evidence_context_truncated={"False":12,"True":1}`, `stop_reason_counts={"verified":13}`
- real-index provider-proposed prompt-size-gate compatibility smoke
  - Result: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `prompt_char_count total=128467 average=9882.1`, `evidence_context_truncated={"False":12,"True":1}`, `stop_reason_counts={"verified":13}`
- real-index provider-proposed prompt-limit CLI compatibility smoke
  - Result: `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `prompt_char_count total=128467 average=9882.1`, `evidence_context_truncated={"False":12,"True":1}`, `stop_reason_counts={"verified":13}`
- real-index provider-proposed prompt-limit CLI failure smoke
  - Result: expected exit code `1` with JSON `1 failed_cases`, `0 passed_cases`, `stop_reason_counts={"patch_failed":1}`, `error_code_counts={"provider_prompt_budget_exceeded":1}`, and `prompt_char_count=9217`
- real-index provider-proposed prompt-limit CLI failure token-metrics smoke
  - Result: expected exit code `1` with JSON `provider_prompt_budget_exceeded`, `provider_tokens_in=0.0`, and `provider_tokens_out=0.0`
- real-index provider-proposed prompt-preflight CLI smoke
  - Result: exit code `0` with JSON `preflight_only=true`, `requested_edit_provider_mode=live`, `live_api_key_present=false`, `prompt_char_count=9217.0`, `provider_tokens_in=0.0`, and `provider_tokens_out=0.0`
- real-index provider-proposed live no-op smoke
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `stop_reason_counts={"verified":1}`, `prompt_char_count=9563.0`, `provider_tokens_in=2526.0`, `provider_tokens_out=1410.0`, `verification_count=1.0`; no-index diff against the source file produced no output
- real-index provider-proposed live semantic smoke, `gemini-2.5-flash`
  - Result: expected failure with `provider_response_truncated` and `Gemini finish_reason: max_tokens`
- real-index provider-proposed live semantic smoke, `gemini-3.1-flash-lite`
  - Result: exit code `1`; provider produced valid JSON and a patch, but verification failed because `max(0, max_length - len(suffix))` violated `truncate_string('abcdef', 2) == 'ab'`
- real-index provider-proposed live semantic smoke, `gemini-3.1-flash-lite-preview`
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=2023.0`, `provider_tokens_out=1370.0`, `verification_count=1.0`; persisted patch added `if max_length <= len(suffix): return text[:max_length]`
- real-index provider-proposed live semantic smoke, file-path validator
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=2471.0`, `provider_tokens_out=1442.0`, `verification_count=1.0`; persisted patch added Windows drive-qualified and backslash absolute-path rejection
- real-index provider-proposed live semantic smoke, email validator
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=2053.0`, `provider_tokens_out=1432.0`, `verification_count=1.0`; persisted patch added consecutive-local-dot rejection while preserving valid dotted local parts
- real-index provider-proposed live target-selection semantic smoke, string truncate
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"utils/string_tools.py":1}`, `baseline_case_count=1`, and `stop_reason_counts={"verified":1}`
- real-index provider-proposed live target-selection semantic smoke, file-path validator
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"utils/validators.py":1}`, `baseline_case_count=1`, and `stop_reason_counts={"verified":1}`
- real-index provider-proposed live target-selection semantic smoke, email validator
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"utils/validators.py":1}`, `baseline_case_count=1`, and `stop_reason_counts={"verified":1}`
- real-index provider-proposed live target-selection three-case suite
  - Result: exit code `0` with JSON `3 passed_cases`, `0 failed_cases`, `baseline_case_count=3`, `target_selection_decision={"selected":3}`, `resolved_target_file={"utils/string_tools.py":1,"utils/validators.py":2}`, `stop_reason_counts={"verified":3}`, `provider_tokens_in=8951.0`, `provider_tokens_out=4220.0`, and `prompt_char_count=29223.0`
- real-index provider-proposed live expanded target-selection suite with `15000` prompt cap
  - Result: expected mixed result with JSON `1 passed_cases`, `1 failed_cases`, `error_code_counts={"provider_prompt_budget_exceeded":1}`; the job-queue case assembled a `17527` character prompt and stopped before provider invocation
- real-index provider-proposed live job-queue target-selection rerun with `22000` prompt cap before expected-behavior clarification
  - Result: expected failure with JSON `1 failed_cases`, `0 passed_cases`, `stop_reason_counts={"verification_timeout":1}`; generated patch called `self.get_queue_size()` inside `with self._lock:`, causing a non-reentrant lock timeout
- real-index provider-proposed live job-queue target-selection rerun after expected-behavior clarification
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":1}`, `resolved_target_file={"async_jobs/job_queue.py":1}`, `stop_reason_counts={"verified":1}`, `provider_tokens_in=5435.0`, `provider_tokens_out=2863.0`, and `prompt_char_count=17671.0`
- real-index provider-proposed live target-selection five-case suite
  - Result: exit code `0` with JSON `5 passed_cases`, `0 failed_cases`, `baseline_case_count=5`, `target_selection_decision={"selected":5}`, `resolved_target_file={"async_jobs/job_queue.py":1,"utils/date_helpers.py":1,"utils/string_tools.py":1,"utils/validators.py":2}`, `stop_reason_counts={"verified":5}`, `provider_tokens_in=16628.0`, `provider_tokens_out=7938.0`, and `prompt_char_count=54039.0`
- real-index provider-proposed live repair probe, `gemini-3.1-flash-lite`
  - Result: exit code `1`; provider invocation failed after DNS retry exhaustion before repair behavior could execute. This exposed provider-layer misclassification, now covered by `provider_invocation_failed`.
- real-index provider-proposed live repair-enabled probe, `gemini-3.1-flash-lite`
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `patch_attempt_count=1.0`, `provider_repair_attempt_count=0.0`, `provider_tokens_in=2045.0`, `provider_tokens_out=1346.0`, and `prompt_char_count=6976.0`; repair was enabled but not exercised because the first patch verified.
- real-index provider-proposed live repair-enabled probe, `gemini-3.1-flash-lite-preview`
  - Result: exit code `0` with JSON `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, `stop_reason_counts={"verified":1}`, `patch_attempt_count=1.0`, `provider_repair_attempt_count=0.0`, `provider_tokens_in=2045.0`, `provider_tokens_out=1346.0`, and `prompt_char_count=6976.0`; repair was enabled but not exercised because the first patch verified.
- real-index provider-proposed live full 13-case suite, `gemini-3.1-flash-lite-preview`
  - Result: exit code `0` with JSON `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `target_selection_decision={"selected":5,"supplied":8}`, `resolved_target_file={"api/routes.py":1,"async_jobs/job_queue.py":2,"cache/cache_manager.py":1,"monitoring/metrics.py":1,"utils/date_helpers.py":2,"utils/string_tools.py":2,"utils/validators.py":4}`, `stop_reason_counts={"verified":13}`, `provider_tokens_in=41601.0`, `provider_tokens_out=21908.0`, `prompt_char_count=139236.0`, `evidence_context_truncated={"False":12,"True":1}`, and `provider_repair_attempt_count=0.0`; repair was enabled but not exercised because all first patches verified.
- real-index direct-provider fake 13-case baseline
  - Result: exit code `0` with JSON `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `planner_context_mode={"direct_provider":13}`, `target_selection_decision={"direct_supplied":13}`, `resolved_target_file` covering the same seven files, `stop_reason_counts={"verified":13}`, `prompt_char_count=85053.0`, and `evidence_context_item_count=0.0`.
- real-index direct-provider live 13-case baseline, `gemini-3.1-flash-lite-preview`
  - Result: exit code `0` with JSON `13 passed_cases`, `0 failed_cases`, `baseline_case_count=10`, `planner_context_mode={"direct_provider":13}`, `target_selection_decision={"direct_supplied":13}`, `resolved_target_file={"api/routes.py":1,"async_jobs/job_queue.py":2,"cache/cache_manager.py":1,"monitoring/metrics.py":1,"utils/date_helpers.py":2,"utils/string_tools.py":2,"utils/validators.py":4}`, `stop_reason_counts={"verified":13}`, `provider_tokens_in=22975.0`, `provider_tokens_out=20903.0`, `prompt_char_count=85053.0`, and `provider_repair_attempt_count=0.0`.
- real-index hard evidence-value fake-provider smoke
  - Result: exit code `0` with JSON `2 passed_cases`, `0 failed_cases`, `baseline_case_count=2`, `target_selection_decision={"selected":2}`, `resolved_target_file={"cache/cache_manager.py":1,"monitoring/metrics.py":1}`, `candidate_file_score_count=43.0`, `target_selection_confidence total=0.5885016336804806`, `prompt_char_count=32829.0`, and `stop_reason_counts={"verified":2}`.
- real-index hard evidence-value live retrieval/evidence smoke, `gemini-3.1-flash-lite-preview`
  - Result: exit code `0` with JSON `2 passed_cases`, `0 failed_cases`, `baseline_case_count=2`, `target_selection_decision={"selected":2}`, `resolved_target_file={"cache/cache_manager.py":1,"monitoring/metrics.py":1}`, `candidate_file_score_count=43.0`, `target_selection_confidence total=0.5885016336804806`, `provider_tokens_in=9474.0`, `provider_tokens_out=4946.0`, `prompt_char_count=32829.0`, and `provider_repair_attempt_count=0.0`.
- real-index hard evidence-value live direct-provider baseline, `gemini-3.1-flash-lite-preview`
  - Result: exit code `0` with JSON `2 passed_cases`, `0 failed_cases`, `baseline_case_count=2`, `planner_context_mode={"direct_provider":2}`, `target_selection_decision={"direct_supplied":2}`, `resolved_target_file={"cache/cache_manager.py":1,"monitoring/metrics.py":1}`, `provider_tokens_in=4917.0`, `provider_tokens_out=4875.0`, `prompt_char_count=18700.0`, and `provider_repair_attempt_count=0.0`.
- real-index hard evidence-value direct-provider target-unavailable smoke
  - Result: expected exit code `1` with JSON `0 passed_cases`, `2 failed_cases`, `baseline_case_count=2`, `planner_context_mode={"direct_provider":2}`, `stop_reason_counts={"patch_failed":2}`, `error_code_counts={"direct_provider_target_required":2}`, `provider_tokens_in=0.0`, `provider_tokens_out=0.0`, and `verification_count=0.0`.
- real-index quality-dimension summary smoke
  - Result: exit code `0` with JSON `2 passed_cases`, `0 failed_cases`, `quality_requires_localization={"False":1,"True":1}`, `quality_verification_kind={"behavior":1,"compile":1}`, `quality_provider_mode={"cache_namespace_invalidation":1,"noop":1}`, `quality_baseline_target_knowledge={"retrieval_localizes":2}`, `target_selection_decision={"selected":1,"supplied":1}`, and `stop_reason_counts={"verified":2}`.
- real-index expanded fake-provider 15-case suite
  - Result: exit code `0` with JSON `15 passed_cases`, `0 failed_cases`, `baseline_case_count=12`, `target_selection_decision={"selected":7,"supplied":8}`, and quality categories covering seven localization-required cases, eight supplied-target cases, three compile no-op cases, and twelve behavior cases.
- real-index expanded live retrieval/evidence 15-case suite, `gemini-3.1-flash-lite-preview`
  - Result: exit code `1` with JSON `14 passed_cases`, `1 failed_case`, `baseline_case_count=12`, `stop_reason_counts={"verified":14,"patch_failed":1}`, `error_code_counts={"provider_invocation_failed":1}`, `quality_baseline_target_knowledge={"retrieval_localizes":15}`, `quality_requires_localization={"False":8,"True":7}`, `quality_verification_kind={"behavior":12,"compile":3}`, `target_selection_decision={"selected":6,"supplied":8}`, `provider_tokens_in=48101.0`, `provider_tokens_out=25438.0`, `prompt_char_count=172065.0`, and `provider_repair_attempt_count=0.0`. The failed case was `validate-file-path-drive-guard-target-selection`, and the failure was a provider/server disconnect before patch verification.
- real-index expanded live direct-provider target-known 15-case comparison, `gemini-3.1-flash-lite-preview`
  - Result: split-artifact evidence after fixing volatile Python cache workspace copies. The initial full run verified nine supplied-target cases; the fresh six-case retry verified all six target-selection cases. Combined result: `15/15 verified`, `baseline_case_count=12`, `planner_context_mode={"direct_provider":15}`, `target_selection_decision={"direct_supplied":15}`, `quality_baseline_target_knowledge={"target_known":15}`, `quality_requires_localization={"False":8,"True":7}`, `quality_verification_kind={"behavior":12,"compile":3}`, `provider_tokens_in=27892.0`, `provider_tokens_out=25778.0`, `prompt_char_count=103753.0`, and `provider_repair_attempt_count=0.0`. This remains a target-known synthesis baseline, not a localization baseline.
- real-index evaluation workspace-copy robustness regression
  - Result: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_copy_case_workspace_ignores_python_cache_artifacts tests\unit\v4\test_real_index_provider_patch_suite.py::test_copy_baseline_workspace_ignores_python_cache_artifacts -q` passed with `2 passed`; the copy path now ignores `__pycache__`, `.pyc`, and `.pyo` artifacts during case and baseline workspace materialization.
- real-index provider suite and harness focused verification after copy fix
  - Result: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_evaluation_harness.py -q` passed with `22 passed`.

Additional current checkpoint evidence:

- `\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_python_ast_fallback.py -q` -> `1 passed`; the parser regression failed before the parent-link fix and passes after it.
- `\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_index_service_contract.py -q` -> `3 passed` after replacing eager adapter exports with lazy package exports; the previous collection error was a circular import.
- `\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q` -> `220 passed, 6 skipped`.
- `\.venv\Scripts\python.exe runtime\v4_cli.py eval-homllm-agent --config configs\default.yaml --source-workspace-root test_repo --workspace-root temp\v4_agent_benchmark_live_3case_work --artifact-root temp\v4_agent_benchmark_live_3case_runs --run-id live-suite-3case-grounded --case-id admin-routes-compile --case-id string-truncate-guard --case-id validate-email-local-dot-guard --live-api-key-env GOOGLE_API_KEY --answer-provider-mode live --provider-repair-attempts 1 --index-skip-vectors --smoke-safe` -> exit code `0`, `3 passed_cases`, `0 failed_cases`; summary artifact: `temp/v4_agent_benchmark_live_3case_runs/live-suite-3case-grounded/evaluation/summary.json`.

## What Is Actually Achieved

v4 has crossed from architecture-only into a verified research-core foundation:

- typed contracts
- v3 adapter boundary
- artifact/ledger discipline
- read-only loop
- local command execution
- policy-filtered subprocess environments for local command execution
- structured command approval-required result
- in-memory approval scope resolution
- append-only approval audit/replay storage
- safe patch application
- explicit rollback for patch-service file changes after failed verification
- verification side-effect detection that blocks success if verification commands create, modify, or delete non-patch files outside ignored cache/artifact paths
- best-effort side-effect cleanup when `rollback_on_failure=True`, restoring modified/deleted non-patch files from the pre-verification snapshot and deleting created non-patch files
- write-verify loop
- deterministic evaluation harness
- fixture write-task suite
- evidence-backed planning
- retrieval-backed planning
- bounded edit proposal seam
- provider-backed proposal seam with fake-provider validation
- provider-backed prompts populated with typed retrieved evidence context rather than only evidence IDs
- provider-backed evidence context constrained by explicit prompt budgets to preserve token efficiency
- provider-backed prompt-size gate can stop oversized prompts before provider calls
- provider prompt-size cap is configurable through `eval-real-index-provider-patch --max-prompt-chars`
- provider prompt-size cap failure is observable at suite and CLI level through `provider_prompt_budget_exceeded`, `patch_failed`, zero verification attempts, and persisted prompt artifacts
- provider token accounting is now based on actual planner telemetry, so prompt-cap denials report zero provider tokens instead of static fake-provider defaults
- no-provider-call prompt preflight exists for live-provider readiness; it exercises real retrieval, target resolution, evidence-context assembly, prompt artifact writing, and prompt-size measurement without invoking the provider
- bounded live-provider synthesis has verified the full previous 13-case real-index suite, most of the expanded 15-case retrieval/evidence suite, and all fifteen target-known direct-provider cases across split artifacts in copied workspaces with Gemini preview; the expanded suite includes three no-op compile cases, five supplied-target semantic patches, seven target-omitted semantic patches, twelve no-patch baselines, and resolved target coverage across seven repository files
- live-provider failures now produced actionable structured classes: missing sandbox network, max-token truncation, invalid JSON dialect, prompt-budget denial, verification failure with rollback, and verification timeout from a deadlocking patch
- provider prompts now include stricter full-file, JSON-encoding, no-op, exact-example, verification-command, and source-text quote escaping requirements
- provider planner normalizes provider output to preserve the original trailing newline when the original file had one
- provider prompts now accept explicit repair context, and the real-index provider suite can run bounded provider repair attempts after verification failure or timeout while aggregating provider token and prompt metrics across attempts
- provider-backed repair orchestration is now extracted into reusable `ProviderWriteVerifyRunner`, so the real-index provider suite no longer owns the planning/write/repair loop directly
- provider invocation failures before any response are now classified separately as retryable `provider_invocation_failed`, with deterministic real-index suite summary coverage
- direct-provider baseline mode exists for the real-index provider suite and CLI; it gives the same provider a known target file and no retrieved evidence context, enabling an internal same-model comparison against the retrieval/evidence path
- direct-provider baselines now make target knowledge explicit: `direct_provider_target_source="actual"` is the target-known synthesis baseline, while `"planner"` exposes target-omitted cases as `direct_provider_target_required` instead of silently giving away ground truth
- two harder target-omitted fake-provider cases now exercise cache namespace invalidation and labelled metrics export, adding lower-confidence target-selection examples for future evidence-value comparisons
- real-index evaluation summaries now expose quality dimensions as categorical metrics, including localization requirement, verification kind, provider mode, verification mode, and baseline target-knowledge class
- evaluation workspace materialization ignores volatile Python cache artifacts for both candidate and baseline copied workspaces, eliminating a Windows `shutil.copytree` failure mode seen during live direct-provider retries
- provider prompt/evidence-context metrics propagated into real-index benchmark summaries
- v3 provider connector adapter for future opt-in live provider tests
- v3 provider primitive-params adapter factory for live benchmark mode without leaking v3 `ModelConfig` outside adapters
- opt-in live provider smoke scaffold
- opt-in live provider patch execution scaffold
- opt-in live provider real-index benchmark mode with provider/model/key-env selection, case listing, validated case filtering, missing-key preflight, and structured CLI preflight errors
- provider-proposed patch planning bridge from evidence to patch request
- deterministic evidence-based target-file selection with structured `selected`, `ambiguous`, and `no_candidates` decisions, wired into provider-proposed patch planning when `target_file` is omitted
- query-aware deterministic target-file selection that boosts meaningful path-token matches from the query while preserving ambiguity when there is no lexical path signal
- provider-proposed planner success telemetry distinguishes supplied targets from evidence-selected targets and includes resolved target file plus selector scores
- real-index benchmark case metrics expose target-selection decisions and resolved target files, so target-omitted coverage is visible in persisted evaluation summaries
- evaluation summaries aggregate string and boolean case metrics under `categorical_metric_counts`, so CLI JSON can show target-selection coverage without inspecting per-case details
- real-index provider-proposed planning smoke
- real-index provider-proposed execution smoke through patch apply and `compileall` verification in a copied workspace
- real-index provider-proposed fifteen-case write benchmark through CLI/API, including twelve behavior-verified semantic non-no-op cases, seven target-omitted cases, no-patch baseline comparison, quality metrics, and provider prompt/response artifacts
- real-index provider benchmark suite profiles through API/CLI, with `core` remaining the default and an `inventory` suite proving the runner can execute a second local fixture repository when the config points at matching retrieval indexes
- inventory fixture benchmark through CLI/API with four fake-provider cases, three behavior baselines, one target-omitted localization case, and resolved target coverage across three files in a second repository fixture
- first MVP local coding-agent task surface: `run_agent_task` and `agent-task` can run a single bounded edit against a workspace, use provider-proposed planning, apply the patch, run verification, allow one provider repair attempt by default, rollback on failure, and persist provider/artifact traces
- first live Gemini MVP `agent-task` smoke using `gemini-3.1-flash-lite-preview` verified a real model-generated edit in a copied inventory fixture workspace: `normalize_sku` changed from `sku.upper()` to `sku.strip().upper()` and behavior verification passed
- `agent-task` verification command parsing now preserves Windows backslash paths and quoted command payloads instead of using POSIX-only splitting
- opt-in `agent-task --prepare-index` can build a run-local v3 index from a template config, pass the generated config into provider patch planning, and report generated index paths and metrics in CLI JSON
- live Gemini `agent-task --prepare-index --index-skip-vectors` smoke verified the combined repo index/load plus model edit plus verification loop in a copied inventory fixture workspace
- first local session-like surface: `run_agent_session` and `agent-session` can prepare a run-local repo index, run a grounded read-only ask, and optionally run one bounded edit/verify sub-run using the same generated config and artifact root
- live Gemini `agent-session --prepare-index --index-skip-vectors` smoke verified a one-shot ask-plus-edit flow in a copied inventory fixture workspace after fixing Windows-invalid colon sub-run IDs
- opt-in provider-grounded session answers: `agent-session --answer-provider-mode live` can synthesize a concise answer from retrieved context, persist answer prompt/response artifacts, expose prompt/token metrics, and fall back to the deterministic read-only summary if answer synthesis fails
- live Gemini `agent-session --answer-provider-mode live --prepare-index --index-skip-vectors` smoke answered an inventory fixture question with a file citation and provider token metrics
- persistent session state: `AgentSessionStore` and `run_agent_session` now write `session.json` with effective config/index metadata and append-only turn records, giving the future headless runner a durable state backbone
- headless MVP agent command: `run_homllm_agent` and `homllm-agent run` now reuse the session path, require persistent session state, and write a compact `trajectory.json` suitable for local benchmark harness consumption
- internal headless-agent benchmark runner: `run_homllm_agent_benchmark` and `eval-homllm-agent` expose a 10-case local suite around `homllm-agent run`, isolate case workspaces, consume `trajectory.json`, and aggregate local benchmark summaries through the existing `EvaluationRunResult` shape
- benchmark pass quality gate: successful cases now require built index evidence when requested, `grounded_answer=sufficient`, `bounded_edit=verified`, `verification=passed`, and both session/trajectory artifacts; incomplete runs receive `benchmark_quality_gate_failed` instead of being counted as passes
- Python fallback index resilience: `_PythonAstNode` now links parent nodes, restoring entity/chunk extraction when tree-sitter language packages are unavailable; the v4 adapter package also uses lazy exports to avoid an index-service import cycle
- live `eval-homllm-agent` three-case slice: run `live-suite-3case-grounded` completed `3/3` with `answer_provider_mode=live`, `trajectory_grounded_answer_status=sufficient` for all cases, `trajectory_bounded_edit_status=verified` for all cases, `trajectory_verification_status=passed` for all cases, `benchmark_quality_gate=passed` for all cases, `provider_tokens_in=12538`, and `provider_tokens_out=4644`
- provider-proposed fixture execution through patch apply and verification
- runnable CLI/API entrypoints

This is a strong foundation for controlled experiments.

## What Is Not Achieved

The active objective is not complete because the system is not yet a production-grade RAG-first coding agent.

Missing or incomplete:

- the expanded 15-case live retrieval/evidence suite has one provider availability failure, while the target-known direct-provider live comparison has split-artifact `15/15` verification with fewer prompt/input tokens; this means the current suite does not yet demonstrate a token-efficiency advantage for evidence context, only that retrieval mode adds localization/evidence grounding while direct-provider mode assumes target knowledge
- no external/live baseline comparison populated for write tasks
- bounded provider repair has fake-provider coverage only; later live repair-enabled probes with `gemini-3.1-flash-lite` and `gemini-3.1-flash-lite-preview` verified first-shot patches with `provider_repair_attempt_count=0.0`, so live provider repair remains unproven rather than failed
- provider prompts are evidence-informed through retrieved target-file context and have produced verified live patches in bounded cases, but they have not been evaluated across a broad task suite
- provider evidence-context prompt budgets are implemented, and live runs now record provider token usage for the internal 15-case retrieval/evidence and direct-provider comparisons; no external or broad live token-efficiency benchmark exists yet
- local prompt character counts, evidence truncation, and live provider token accounting are measurable, but they have not been compared against an external/live baseline
- hard prompt-size gating exists and is tested before provider invocation; live runs used a safe prompt cap, but no live run has intentionally hit the cap
- prompt preflight reduces live-run risk, but it is not a substitute for multi-case live synthesis evaluation
- omitted-target provider-proposed write planning is covered by only seven real-index benchmark cases
- semantic real-index write coverage is still narrow: twelve hand-authored behavior cases in the core fixture plus three behavior cases in the local inventory fixture, all Python and synthetic
- the new `eval-homllm-agent` suite has a real live Gemini three-case slice, but the full 10-case live suite has not yet been executed in this slice
- live-provider indexed-repo provider-proposed patch execution has verified most of the current internal 15-case retrieval/evidence suite, all target-known direct-provider cases, one inventory `agent-task` smoke, and one inventory `agent-task --prepare-index` smoke; no external repository/task suite has been run
- the direct-provider baseline is target-known, so it does not test localization, ambiguous repository navigation, or multi-file planning; it is an internal baseline, not a Cursor/Codex/SWE-agent comparison
- arbitrary verification-command side effects are detected and can be cleaned up from local snapshots when rollback is enabled, but this is not a substitute for OS-level sandbox isolation
- command subprocesses no longer inherit arbitrary parent-process environment variables by default, but env filtering is not a substitute for OS-level sandbox isolation
- no OS-level sandbox backend
- no approval UX or multi-process approval locking
- no interactive product-facing session manager; `agent-session` and `homllm-agent run` are one-shot local flows, not a REPL or autonomous multi-turn coding agent
- persistent `session.json` and headless `trajectory.json` now exist, but the runner does not yet consume prior turns for true multi-turn task continuation
- automatic "index this repo then ask/edit" now exists as opt-in local CLI/API flags and through `homllm-agent run`, and local benchmark summaries now exist through `eval-homllm-agent`; repeated task dialogue, memory-aware planning, and multi-step autonomous planning are still incomplete
- provider-grounded session answering has one live fixture smoke and unit coverage, but no broad Q&A benchmark or external repository validation
- no broad task coverage beyond local deterministic Python patch fixtures
- no token-efficiency comparison for full write workflows

## Completion Decision

Do not mark the goal complete.

The correct next milestone is:

> M6 next slice: execute the full 10-case live `eval-homllm-agent` suite, inspect every trajectory and quality-gate failure, and then decide whether bounded live repair or benchmark-case expansion is the next highest-value work.

Live-provider benchmark execution must remain opt-in and fake-provider-first by default; the benchmark runner now exists, but the full MVP is not complete until live evidence and benchmark artifacts prove the end-to-end loop under realistic cases.
