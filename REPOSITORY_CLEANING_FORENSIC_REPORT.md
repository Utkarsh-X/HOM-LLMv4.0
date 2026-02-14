# REPOSITORY CLEANING FORENSIC REPORT

Read-only structural audit. No code refactor/deletion was performed. Findings are from static inspection and repository reference scanning.

## 1. High Level Structural Map

| Directory | Purpose (Inferred) | Referenced Externally | Production vs Experimental | Abandonment Signal | Status |
|---|---|---:|---|---|---|
| `artifacts` | Generated run artifacts and telemetry payloads | 15 refs | Experimental artifacts | Medium | **EXPERIMENTAL** |
| `configs` | Runtime and experiment configuration files | 17 refs | Production | Low | **ACTIVE** |
| `diagnostics` | Standalone diagnostic scripts and inspection helpers | 2 refs | Experimental tooling | Medium | **EXPERIMENTAL** |
| `docs` | Human reports/plans; mostly process/history docs | 1 refs | Documentation | Medium | **LEGACY** |
| `eval` | Evaluation harness, judge runner, run artifacts, and forensic writeups | 21 refs | Experimental+Ops | Low | **EXPERIMENTAL** |
| `files` | Architecture/reference markdown bundle | 8 refs | Documentation | High | **LEGACY** |
| `indexes` | Local index/storage artifacts used by runtime | 11 refs | Runtime artifacts | Low | **ACTIVE** |
| `logs` | Ad-hoc logs | 0 refs | Operational artifacts | Medium | **UNCLEAR** |
| `r2` | Historical requirement/problem docs | 0 refs | Legacy documentation | High | **LEGACY** |
| `runtime` | CLI entrypoints and orchestration for indexing/query runtime | 6 refs | Production | Low | **ACTIVE** |
| `src` | Production pipeline code (indexer/retrieval/ranking/context/generation/intelligence) | 24 refs | Production | Low | **ACTIVE** |
| `test_repo` | Synthetic corpus used as indexed codebase/evaluation fixture | 2 refs | Experimental fixture | Low | **ACTIVE** |
| `tests` | Automated test suite for active modules | 8 refs | Production guardrail | Low | **ACTIVE** |

Notes:
- `src/`, `runtime/`, `configs/`, `indexes/`, and `tests/` are active system-critical directories.
- `docs/`, `files/`, and `r2/` contain mostly planning/history material and are high-clutter surfaces.
- `eval/` mixes active harness code with large historical artifacts, causing operational drift.

## 2. Unused Or Unreferenced Files (Python)

Static scan evaluated **299 Python files** with checks for: imports, CLI entrypoint (`__main__`), config references, and test references.

| Category | Count |
|---|---:|
| DEFINITELY UNUSED | 9 |
| LIKELY UNUSED | 31 |
| EXPERIMENTAL ONLY | 30 |
| TEST ONLY | 90 |
| CORE DEPENDENCY | 139 |

### 2.1 Categorized File Table

| File | Category | Imported By | CLI Entrypoint | Config Refs | Test Refs | Other Refs |
|---|---|---:|---|---:|---:|---:|
| `src/homllm/alignment/grounding.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/alignment/policy/policy_mapper.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/alignment/semantic.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/alignment/structural.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/common/config.py` | CORE DEPENDENCY | 14 | No | 10 | 1 | 5 |
| `src/homllm/common/exceptions.py` | CORE DEPENDENCY | 2 | No | 152 | 0 | 1 |
| `src/homllm/common/hf_cache.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/common/types.py` | CORE DEPENDENCY | 33 | No | 0 | 0 | 1 |
| `src/homllm/context/applier.py` | CORE DEPENDENCY | 4 | No | 0 | 1 | 1 |
| `src/homllm/context/assembler.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 2 |
| `src/homllm/context/budget.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 4 |
| `src/homllm/context/deduper.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/context/diff.py` | CORE DEPENDENCY | 3 | No | 0 | 1 | 1 |
| `src/homllm/context/integration_controller.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/context/interfaces.py` | CORE DEPENDENCY | 52 | No | 147 | 1 | 10 |
| `src/homllm/context/pipeline.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 16 |
| `src/homllm/context/scorer.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/context/stitcher.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/context/synthesis_profile.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/explanation_gap/classifier_stub.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/explanation_gap/constants.py` | CORE DEPENDENCY | 5 | No | 0 | 0 | 2 |
| `src/homllm/explanation_gap/embedding_refinement.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/explanation_gap/history.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 2 |
| `src/homllm/explanation_gap/interfaces.py` | CORE DEPENDENCY | 8 | No | 147 | 1 | 10 |
| `src/homllm/explanation_gap/pipeline.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 16 |
| `src/homllm/explanation_gap/rules.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 7 |
| `src/homllm/generation/adapter.py` | CORE DEPENDENCY | 4 | No | 0 | 0 | 7 |
| `src/homllm/generation/config.py` | CORE DEPENDENCY | 1 | No | 10 | 1 | 5 |
| `src/homllm/generation/hallucination.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/generation/interfaces.py` | CORE DEPENDENCY | 9 | No | 147 | 1 | 10 |
| `src/homllm/generation/parser.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 3 |
| `src/homllm/generation/providers/gemini.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 3 |
| `src/homllm/generation/providers/generic_http.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 3 |
| `src/homllm/generation/providers/local.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 3 |
| `src/homllm/generation/providers/openai.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 3 |
| `src/homllm/generation/template_loader.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 2 |
| `src/homllm/indexer/confidence_scorer.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/indexer/embedder.py` | CORE DEPENDENCY | 8 | No | 0 | 0 | 5 |
| `src/homllm/indexer/entity_extractor.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/indexer/graph_builder.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 7 |
| `src/homllm/indexer/graph_resolver.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 3 |
| `src/homllm/indexer/hierarchical_chunker.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 6 |
| `src/homllm/indexer/incremental_indexer.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 5 |
| `src/homllm/indexer/interfaces.py` | CORE DEPENDENCY | 12 | No | 147 | 1 | 10 |
| `src/homllm/indexer/parser.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 3 |
| `src/homllm/indexer/pipeline.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 16 |
| `src/homllm/indexer/scanner.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/indexer/storage/duckdb_adapter.py` | CORE DEPENDENCY | 8 | No | 0 | 0 | 2 |
| `src/homllm/indexer/storage/filesystem_adapter.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 2 |
| `src/homllm/indexer/storage/lancedb_adapter.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 4 |
| `src/homllm/indexer/storage/tantivy_adapter.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 3 |
| `src/homllm/instability/bucketing.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/instability/constants.py` | CORE DEPENDENCY | 4 | No | 0 | 0 | 2 |
| `src/homllm/instability/interfaces.py` | CORE DEPENDENCY | 12 | No | 147 | 1 | 10 |
| `src/homllm/instability/pipeline.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 16 |
| `src/homllm/instability/signals/answer_structure.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/instability/signals/embedding_consistency.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/instability/signals/failure_frequency.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/instability/signals/metadata_variance.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/instability/signals/retrieval_overlap.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/instability/utils.py` | CORE DEPENDENCY | 4 | No | 0 | 2 | 7 |
| `src/homllm/intelligence/actions/level1/engine.py` | CORE DEPENDENCY | 3 | No | 41 | 0 | 1 |
| `src/homllm/intelligence/actions/level1/plan.py` | CORE DEPENDENCY | 11 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/actions/level1/resolver.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 3 |
| `src/homllm/intelligence/actions/level1/rules.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 7 |
| `src/homllm/intelligence/actions/level2/engine.py` | CORE DEPENDENCY | 3 | No | 41 | 0 | 1 |
| `src/homllm/intelligence/actions/level2/gaps.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/actions/level2/graph.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 2 |
| `src/homllm/intelligence/actions/level2/obligations.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/actions/level2/plan.py` | CORE DEPENDENCY | 10 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/actions/level3/engine.py` | CORE DEPENDENCY | 3 | No | 41 | 0 | 1 |
| `src/homllm/intelligence/actions/level3/graph.py` | CORE DEPENDENCY | 5 | No | 0 | 0 | 2 |
| `src/homllm/intelligence/actions/level3/invariants.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/actions/level3/load.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/actions/level3/paths.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/actions/level3/plan.py` | CORE DEPENDENCY | 12 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/actions/level3/planner.py` | CORE DEPENDENCY | 2 | No | 100 | 0 | 1 |
| `src/homllm/intelligence/assertion_readability/collector.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/assertion_readability/evaluator.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/assertion_readability/interfaces.py` | CORE DEPENDENCY | 7 | No | 147 | 1 | 10 |
| `src/homllm/intelligence/audit/collector.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/audit/interfaces.py` | CORE DEPENDENCY | 2 | No | 147 | 1 | 10 |
| `src/homllm/intelligence/controller.py` | CORE DEPENDENCY | 11 | No | 0 | 3 | 9 |
| `src/homllm/intelligence/diagnostics/context_level3/inspect_alignment_summary.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/diagnostics/context_level3/inspect_explanatory_roles.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/diagnostics/context_level3/inspect_query_intent.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/diagnostics/controller.py` | CORE DEPENDENCY | 3 | No | 0 | 3 | 9 |
| `src/homllm/intelligence/diagnostics/inspect_context.py` | CORE DEPENDENCY | 9 | No | 0 | 0 | 2 |
| `src/homllm/intelligence/diagnostics/inspect_context_relations.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/diagnostics_runner.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/fixer_config.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/interfaces.py` | CORE DEPENDENCY | 23 | No | 147 | 1 | 10 |
| `src/homllm/intelligence/mechanical_fixer.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/reasoning_contracts/builder.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 7 |
| `src/homllm/intelligence/reasoning_contracts/collector.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/reasoning_contracts/enforcer.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/reasoning_contracts/guards.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/reasoning_contracts/interfaces.py` | CORE DEPENDENCY | 9 | No | 147 | 1 | 10 |
| `src/homllm/intelligence/reasoning_diagnostic/collector.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/reasoning_diagnostic/evaluator.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 0 |
| `src/homllm/intelligence/reasoning_diagnostic/interfaces.py` | CORE DEPENDENCY | 3 | No | 147 | 1 | 10 |
| `src/homllm/ranking/adaptive_weights.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/ranking/confidence.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/ranking/dedup_structural.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/ranking/features.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 3 |
| `src/homllm/ranking/fusion.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/ranking/graph_propagation.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/ranking/graph_proximity.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/ranking/interfaces.py` | CORE DEPENDENCY | 12 | No | 147 | 1 | 10 |
| `src/homllm/ranking/mmr_selection.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/ranking/pipeline.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 16 |
| `src/homllm/ranking/reranker.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 3 |
| `src/homllm/ranking/set_optimizer.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 0 |
| `src/homllm/ranking/signal_profile.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/remediation/adapter.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 7 |
| `src/homllm/remediation/interfaces.py` | CORE DEPENDENCY | 5 | No | 147 | 1 | 10 |
| `src/homllm/remediation/matrix.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 1 |
| `src/homllm/remediation/pipeline.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 16 |
| `src/homllm/retrieval/bm25.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 4 |
| `src/homllm/retrieval/budget.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 4 |
| `src/homllm/retrieval/deduplication.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 2 |
| `src/homllm/retrieval/diversity_mmr.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 0 |
| `src/homllm/retrieval/expander.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/retrieval/granularity_booster.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 2 |
| `src/homllm/retrieval/granularity_strategy.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 2 |
| `src/homllm/retrieval/graph_stitch.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 3 |
| `src/homllm/retrieval/hybrid.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 6 |
| `src/homllm/retrieval/interfaces.py` | CORE DEPENDENCY | 33 | No | 147 | 1 | 10 |
| `src/homllm/retrieval/pipeline.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 16 |
| `src/homllm/retrieval/precision_recovery.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/retrieval/preparer.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 5 |
| `src/homllm/retrieval/vector.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 5 |
| `src/homllm/sufficiency/intent.py` | CORE DEPENDENCY | 3 | No | 0 | 0 | 2 |
| `src/homllm/sufficiency/interfaces.py` | CORE DEPENDENCY | 11 | No | 147 | 1 | 10 |
| `src/homllm/sufficiency/pipeline.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 16 |
| `src/homllm/sufficiency/signals/rule.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/sufficiency/signals/semantic.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 1 |
| `src/homllm/sufficiency/signals/structural.py` | CORE DEPENDENCY | 1 | No | 0 | 0 | 2 |
| `src/homllm/sufficiency/veto.py` | CORE DEPENDENCY | 2 | No | 0 | 0 | 2 |
| `bootstrap.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `delmelater.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `runtime/logger.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `runtime/token_attribution.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `setup.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `src/homllm/alignment/analyzer.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `src/homllm/alignment/classifier.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `src/homllm/alignment/policy/policy_engine.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `src/homllm/alignment/policy/policy_types.py` | DEFINITELY UNUSED | 0 | No | 0 | 0 | 0 |
| `diagnostics/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/common/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/common/formatters.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/common/loaders.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/common/utils.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 2 | 7 |
| `diagnostics/context/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/context/inspect_context.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 2 |
| `diagnostics/context/inspect_context_relations.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/context_level3/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/context_level3/inspect_alignment_summary.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/context_level3/inspect_cognitive_load.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/context_level3/inspect_concept_gaps.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/context_level3/inspect_explanatory_roles.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/context_level3/inspect_query_intent.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/embedding/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/embedding/inspect_embeddings.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/reranking/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/reranking/inspect_reranking.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/retrieval/__init__.py` | EXPERIMENTAL ONLY | 0 | No | 206 | 5 | 9 |
| `diagnostics/retrieval/inspect_retrieval.py` | EXPERIMENTAL ONLY | 0 | No | 0 | 0 | 1 |
| `diagnostics/run_diagnostics.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 1 |
| `diagnostics/verify.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 0 |
| `eval/compare_context_runs.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 0 |
| `eval/compare_runs.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 1 |
| `eval/run_experiment.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 3 |
| `eval/run_intelligence_comparison.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 0 |
| `eval/run_judge.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 3 |
| `indexes_maker.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 1 |
| `runtime/index_repo.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 2 |
| `runtime/run_query.py` | EXPERIMENTAL ONLY | 0 | Yes | 0 | 0 | 6 |
| `runtime/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/alignment/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/alignment/interfaces.py` | LIKELY UNUSED | 0 | No | 147 | 1 | 10 |
| `src/homllm/alignment/policy/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/common/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/context/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/explanation_gap/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/generation/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/generation/providers/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/generation/templates/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/indexer/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/indexer/storage/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/instability/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/instability/signals/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/actions/level1/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/actions/level2/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/actions/level3/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/assertion_readability/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/audit/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/diagnostics/context_level3/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/diagnostics/context_level3/inspect_cognitive_load.py` | LIKELY UNUSED | 0 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/diagnostics/context_level3/inspect_concept_gaps.py` | LIKELY UNUSED | 0 | No | 0 | 0 | 1 |
| `src/homllm/intelligence/reasoning_contracts/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/intelligence/reasoning_diagnostic/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/ranking/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/ranking/dedup.py` | LIKELY UNUSED | 0 | No | 0 | 0 | 2 |
| `src/homllm/remediation/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/retrieval/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/sufficiency/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `src/homllm/sufficiency/signals/__init__.py` | LIKELY UNUSED | 0 | No | 206 | 5 | 9 |
| `test_repo/api/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/api/dependencies.py` | TEST ONLY | 0 | No | 38 | 0 | 1 |
| `test_repo/api/routes.py` | TEST ONLY | 0 | No | 67 | 1 | 3 |
| `test_repo/async_jobs/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/async_jobs/batch_processor.py` | TEST ONLY | 0 | No | 34 | 0 | 2 |
| `test_repo/async_jobs/job_queue.py` | TEST ONLY | 0 | No | 7 | 0 | 2 |
| `test_repo/async_jobs/worker.py` | TEST ONLY | 0 | No | 7 | 0 | 1 |
| `test_repo/cache/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/cache/cache_manager.py` | TEST ONLY | 0 | No | 41 | 0 | 1 |
| `test_repo/cache/decorators.py` | TEST ONLY | 0 | No | 66 | 0 | 1 |
| `test_repo/cache/redis_client.py` | TEST ONLY | 0 | No | 62 | 0 | 1 |
| `test_repo/config.py` | TEST ONLY | 0 | No | 10 | 1 | 5 |
| `test_repo/core/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/core/exceptions.py` | TEST ONLY | 0 | No | 152 | 0 | 1 |
| `test_repo/core/interfaces.py` | TEST ONLY | 0 | No | 147 | 1 | 10 |
| `test_repo/database/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/database/adapters/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/database/adapters/postgres.py` | TEST ONLY | 0 | No | 33 | 0 | 1 |
| `test_repo/database/adapters/sqlite_legacy.py` | TEST ONLY | 0 | No | 8 | 0 | 0 |
| `test_repo/database/connection.py` | TEST ONLY | 0 | No | 35 | 0 | 2 |
| `test_repo/main.py` | TEST ONLY | 0 | Yes | 70 | 2 | 9 |
| `test_repo/monitoring/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/monitoring/decorators.py` | TEST ONLY | 0 | No | 66 | 0 | 1 |
| `test_repo/monitoring/metrics.py` | TEST ONLY | 0 | No | 7 | 0 | 1 |
| `test_repo/monitoring/tracer.py` | TEST ONLY | 0 | No | 66 | 0 | 0 |
| `test_repo/optimization/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/optimization/execution_engine.py` | TEST ONLY | 0 | No | 41 | 0 | 1 |
| `test_repo/optimization/query_optimizer.py` | TEST ONLY | 0 | No | 157 | 0 | 14 |
| `test_repo/optimization/query_planner.py` | TEST ONLY | 0 | No | 100 | 0 | 1 |
| `test_repo/search_engine/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/search_engine/filters.py` | TEST ONLY | 0 | No | 9 | 0 | 1 |
| `test_repo/search_engine/indexer.py` | TEST ONLY | 0 | No | 40 | 0 | 6 |
| `test_repo/search_engine/ranking.py` | TEST ONLY | 0 | No | 36 | 0 | 2 |
| `test_repo/security/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/security/auth_manager.py` | TEST ONLY | 0 | No | 7 | 0 | 1 |
| `test_repo/security/decorators.py` | TEST ONLY | 0 | No | 66 | 0 | 1 |
| `test_repo/security/hashing.py` | TEST ONLY | 0 | No | 6 | 0 | 0 |
| `test_repo/utils/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `test_repo/utils/date_helpers.py` | TEST ONLY | 0 | No | 4 | 0 | 0 |
| `test_repo/utils/string_tools.py` | TEST ONLY | 0 | No | 6 | 0 | 0 |
| `test_repo/utils/validators.py` | TEST ONLY | 0 | No | 34 | 0 | 2 |
| `tests/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `tests/conftest.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/determinism/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `tests/determinism/test_context_determinism.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/determinism/test_generation_determinism.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/determinism/test_indexer_determinism.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/determinism/test_ranking_determinism.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/determinism/test_retrieval_determinism.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/integration/test_diagnostic_stack_integration.py` | TEST ONLY | 0 | No | 0 | 0 | 1 |
| `tests/integration/test_intelligence_pipeline.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/test_entity_centric_indexing.py` | TEST ONLY | 0 | Yes | 0 | 0 | 0 |
| `tests/test_plan_b_retrieval.py` | TEST ONLY | 0 | Yes | 0 | 0 | 0 |
| `tests/test_plan_c_mechanical_fixer.py` | TEST ONLY | 0 | Yes | 0 | 0 | 0 |
| `tests/unit/__init__.py` | TEST ONLY | 0 | No | 206 | 5 | 9 |
| `tests/unit/test_alignment.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_alignment_classifier.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_alignment_policy.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_assertion_readability.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_ast_call_graph.py` | TEST ONLY | 0 | No | 0 | 0 | 2 |
| `tests/unit/test_audit_collector.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_context_applier.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_context_assembler.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_context_imports.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_contract_enforcer.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_diagnostic_interface.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_diagnostics_token_alignment.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_eval_file_structure.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_explanation_gap_layer.py` | TEST ONLY | 0 | No | 0 | 0 | 1 |
| `tests/unit/test_fixer_config.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_generation_imports.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_incremental_indexing.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_indexer_imports.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_instability_layer.py` | TEST ONLY | 0 | No | 0 | 0 | 1 |
| `tests/unit/test_intelligence_controller.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_intelligence_levels_parsing.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_lancedb_adapter.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_level1_action_engine.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_level2_action_engine.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_level3_action_engine.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_phase3c_guards.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_ranking_imports.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_reasoning_contracts.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_reasoning_diagnostic.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_remediation_layer.py` | TEST ONLY | 0 | No | 0 | 0 | 1 |
| `tests/unit/test_retrieval_imports.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_scope_injection.py` | TEST ONLY | 0 | No | 0 | 0 | 3 |
| `tests/unit/test_sufficiency_layer.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |
| `tests/unit/test_symbol_resolution.py` | TEST ONLY | 0 | No | 0 | 0 | 2 |
| `tests/unit/test_token_attribution.py` | TEST ONLY | 0 | No | 0 | 0 | 0 |

Static-scan caveat: package `__init__.py` modules can be under-counted by import-only heuristics and may appear as "likely unused" despite legitimate package semantics.

## 3. Configuration Drift Analysis

### 3.1 Config Files Present

- `configs/default.yaml`
- `configs/phase3_covp10.yaml`
- `configs/secrets.yaml` well stores the keys

### 3.2 Recent Run Usage (from `eval/runs/*/run_info.json`)

| Config Path | Run Count |
|---|---:|
| `configs\default.yaml` | 3 |
| `configs\phase3_covp10.yaml` | 2 |

### 3.3 Drift Findings

- `configs/phase3_covp10.yaml` is a near-duplicate of `configs/default.yaml`; only `ranking.set_optimization.w_coverage` and `ranking.set_optimization.w_dispersion` differ.
- `retrieval.bm25.engine` and `retrieval.vector.engine` are defined in config but not consumed by runtime retrieval wiring (engine selection is hardwired by class construction).
- `evaluation.*` config block is modeled in `src/homllm/common/config.py` but not actively used by `eval/run_experiment.py` or `eval/run_judge.py` execution path.
- `eval/judge_config.json` and `eval/judge_config_alt.json` are shadow configs; diff is currently: api_key: <redacted> differs.
- `configs/secrets.example.yaml` appears deleted in git status, leaving no checked-in secret template.

## 4. Ranking / Retrieval Complexity Audit

### 4.1 Suspicious Redundancy / Over-Architecture

- `src/homllm/ranking/pipeline.py:129`: `ranking_synthesis_score` is computed but not consumed downstream.
- `src/homllm/ranking/set_optimizer.py:41` and `src/homllm/ranking/set_optimizer.py:42`: `base_weight_vector` and `effective_weight_vector` currently store identical values; adaptive distinction no longer exists.
- `src/homllm/ranking/pipeline.py:224-391`: Phase-2 adaptive weighting + two-pass + MMR codepaths still exist while set-optimizer is also active, increasing objective layering complexity.
- `src/homllm/retrieval/pipeline.py:217`: `apply_mmr_in_merge` is hardcoded `False`; merge-time MMR branch is effectively disabled.
- `src/homllm/retrieval/pipeline.py:326` and `src/homllm/retrieval/pipeline.py:334`: `metadata["mmr_ms"]` assigned twice (later value overwrites earlier).
- `src/homllm/retrieval/pipeline.py:10`: `hashlib` import appears unused.

### 4.2 Metrics/Telemetry That Look Orphaned or Weakly Consumed

- Set-optimizer telemetry includes high-detail fields (`marginal_gain_breakdown`, weight vectors), but no downstream consumer currently enforces/validates them.
- Retrieval MMR telemetry duplicates fields in both pipeline-level timing and merger metrics dict.

## 5. Context Assembly Layer Audit

| Area | Evidence | Classification |
|---|---|---|
| Synthesis/Integration profiling in context pipeline | `src/homllm/context/pipeline.py:103-140` | DUPLICATED RESPONSIBILITY (behavior shaping beyond pure assembly) |
| Budget modulation via integration pressure | `src/homllm/context/budget.py:31-45` | DUPLICATED RESPONSIBILITY |
| File diversity decay in scorer | `src/homllm/context/scorer.py:23` and `src/homllm/context/scorer.py:120-128` | DUPLICATED RESPONSIBILITY (overlaps ranking dispersion objective) |
| Structural/novelty/coherence forced to zero | `src/homllm/context/scorer.py:78-80` | LEGACY (implemented signals currently bypassed) |
| Helper methods for structural/novelty/coherence | `src/homllm/context/scorer.py:147-212` | UNUSED (not called in active score path) |
| Preserve-order disabled branch in budget allocator | `src/homllm/context/budget.py:49-58`; only caller sets `preserve_order=True` at `src/homllm/context/pipeline.py:205` | UNUSED (unreachable in current pipeline wiring) |
| Provenance telemetry fields (`context_drop_trace`, `context_synthesis`, `context_integration`) | Emitted in `src/homllm/context/pipeline.py:253-269`, consumed by `runtime/run_query.py:869-878` | ACTIVE AND NECESSARY |

## 6. Evaluation / Judge Infrastructure Drift

Findings:
- `eval/run_experiment.py:430-432`: `--telemetry-print` uses `store_true` with `default=True`, so behavior is effectively always enabled (flag semantics drift).
- `eval/run_experiment.py:261` and `eval/run_experiment.py:269`: duplicate `answer_text` key assignment in response dict.
- `eval/run_judge.py:70`: output JSONL is append-only; reruns on same output path create duplicate records.
- Multiple run folders include partially rerun artifacts; historical eval data and current eval data are intermingled.
- Two judge config files exist (`eval/judge_config.json`, `eval/judge_config_alt.json`) with shadowed purpose and credential divergence.

## 7. Documentation & Markdown Clutter

| Document | Category | Reason |
|---|---|---|
| `pytest_cache/README.md` | ARCHIVE | Historical/report artifact with low runtime linkage. |
| `CompleteArchitecturePlan_Refined.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `COMPREHENSIVE_REVIEW.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `diagnostics/README.md` | KEEP | Entry guide for diagnostics scripts. |
| `diagnostics/reports/summary/embedding_analysis.md` | ARCHIVE | Historical/report artifact with low runtime linkage. |
| `docs/diagnostic_systems_guide.md` | ARCHIVE | Documentation appears historical or superseded by newer reports. |
| `docs/eval_folder_guide_and_report.md` | ARCHIVE | Documentation appears historical or superseded by newer reports. |
| `docs/indexer plans/00_START_HERE_EXECUTIVE_SUMMARY.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/indexer plans/GAP_ANALYSIS_AND_IMPLEMENTATION.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/indexer plans/IMPL_GAP1_SCOPE_INJECTION.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/indexer plans/IMPL_GAP2_AST_CALL_GRAPHS.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/indexer plans/IMPL_GAP3_SYMBOL_RESOLUTION.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/indexer plans/IMPL_GAP4_INCREMENTAL_INDEXING.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/intelligence_diagnostics_signals.md` | ARCHIVE | Documentation appears historical or superseded by newer reports. |
| `docs/PHASE3_CONTROLLED_WEIGHT_CALIBRATION_REPORT_20260212.md` | KEEP | Recent experiment forensics still relevant to active stability work. |
| `docs/ranking plans/RANKING SYSTEM Architectural Evolution Plan.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/retrieval plans/00_RETRIEVAL_IMPLEMENTATION_PRIORITY.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/retrieval plans/RETRIEVAL_PHASE_GAP_ANALYSIS.md` | ARCHIVE | Planning docs; implementation mostly landed or superseded. |
| `docs/selection_drift_forensic_report_addendum_20260213.md` | KEEP | Recent experiment forensics still relevant to active stability work. |
| `eval/deep_diagnostics_analysis_latest_run.md` | ARCHIVE | Historical/report artifact with low runtime linkage. |
| `eval/diagnostics_comparison_plan_abc.md` | ARCHIVE | Historical/report artifact with low runtime linkage. |
| `eval/diagnostics_review_plans_abc.md` | ARCHIVE | Historical/report artifact with low runtime linkage. |
| `eval/forensic_report/capability_gap_matrix.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/forensic_report/CAPABILITY_GAP_REPORT.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/forensic_report/cross_run_consistency.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/forensic_report/cursor_advantage_breakdown.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/forensic_report/executive_summary.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/forensic_report/per_query_analysis.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/forensic_report/root_cause_hypotheses.md` | MERGE | Overlapping forensic docs can be consolidated into one canonical report. |
| `eval/quick_analysis_run_20260204_145217.md` | ARCHIVE | Point-in-time analysis snapshot. |
| `files/00_ARCHITECTURE_OVERVIEW.md` | MERGE | Conceptual docs overlap with docs/ and root reports. |
| `files/01_INDEXING_PHASE.md` | MERGE | Conceptual docs overlap with docs/ and root reports. |
| `files/02_RETRIEVAL_PHASE.md` | MERGE | Conceptual docs overlap with docs/ and root reports. |
| `files/03_IMPLEMENTATION_ROADMAP.md` | MERGE | Conceptual docs overlap with docs/ and root reports. |
| `files/04_PERFORMANCE_OPTIMIZATIONS.md` | MERGE | Conceptual docs overlap with docs/ and root reports. |
| `files/README.md` | MERGE | Conceptual docs overlap with docs/ and root reports. |
| `graph_cache_beam.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `latency_breakdown.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `latency_debug_beam_cache.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `PHASE_5_SUMMARY.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `post_merge_60.md` | MERGE | Root-level report clutter; should be merged into canonical architecture/perf docs. |
| `r2/diagnostic_stack_integration_verification_report.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/diagnostic_telemetry_path_and_flags.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_1_intent_gated_sufficiency_layer_architectural_plan.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_1_verification_and_evaluation.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_2_action_remediation_layer_specification.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_2_verification.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_3_cross_run_instability_detection_frozen_design_spec.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_3_verification.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_4_structural_explanation_gap_detection_frozen_design.md` | ARCHIVE | Historical requirement/problem statements. |
| `r2/problem_4_verification.md` | ARCHIVE | Historical requirement/problem statements. |
| `runtime/README.md` | KEEP | Operational runtime CLI documentation. |

## 8. Test Suite Alignment

| Test File | Status | Rationale |
|---|---|---|
| `tests/determinism/test_context_determinism.py` | VALID | Covers active module behavior. |
| `tests/determinism/test_generation_determinism.py` | VALID | Covers active module behavior. |
| `tests/determinism/test_indexer_determinism.py` | VALID | Covers active module behavior. |
| `tests/determinism/test_ranking_determinism.py` | VALID | Covers active module behavior. |
| `tests/determinism/test_retrieval_determinism.py` | VALID | Covers active module behavior. |
| `tests/integration/test_diagnostic_stack_integration.py` | LEGACY | Targets older experimental layers that are under active cleanup pressure. |
| `tests/integration/test_intelligence_pipeline.py` | VALID | Covers active module behavior. |
| `tests/test_entity_centric_indexing.py` | VALID | Covers active module behavior. |
| `tests/test_plan_b_retrieval.py` | VALID | Covers active module behavior. |
| `tests/test_plan_c_mechanical_fixer.py` | LEGACY | Targets older experimental layers that are under active cleanup pressure. |
| `tests/unit/test_alignment.py` | VALID | Covers active module behavior. |
| `tests/unit/test_alignment_classifier.py` | VALID | Covers active module behavior. |
| `tests/unit/test_alignment_policy.py` | VALID | Covers active module behavior. |
| `tests/unit/test_assertion_readability.py` | VALID | Covers active module behavior. |
| `tests/unit/test_ast_call_graph.py` | VALID | Covers active module behavior. |
| `tests/unit/test_audit_collector.py` | VALID | Covers active module behavior. |
| `tests/unit/test_context_applier.py` | VALID | Covers active module behavior. |
| `tests/unit/test_context_assembler.py` | VALID | Covers active module behavior. |
| `tests/unit/test_context_imports.py` | REDUNDANT | Import-smoke checks overlap with broader functional tests. |
| `tests/unit/test_contract_enforcer.py` | VALID | Covers active module behavior. |
| `tests/unit/test_diagnostic_interface.py` | VALID | Covers active module behavior. |
| `tests/unit/test_diagnostics_token_alignment.py` | VALID | Covers active module behavior. |
| `tests/unit/test_eval_file_structure.py` | VALID | Covers active module behavior. |
| `tests/unit/test_explanation_gap_layer.py` | VALID | Covers active module behavior. |
| `tests/unit/test_fixer_config.py` | LEGACY | Targets older experimental layers that are under active cleanup pressure. |
| `tests/unit/test_generation_imports.py` | REDUNDANT | Import-smoke checks overlap with broader functional tests. |
| `tests/unit/test_incremental_indexing.py` | VALID | Covers active module behavior. |
| `tests/unit/test_indexer_imports.py` | REDUNDANT | Import-smoke checks overlap with broader functional tests. |
| `tests/unit/test_instability_layer.py` | LEGACY | Targets older experimental layers that are under active cleanup pressure. |
| `tests/unit/test_intelligence_controller.py` | VALID | Covers active module behavior. |
| `tests/unit/test_intelligence_levels_parsing.py` | VALID | Covers active module behavior. |
| `tests/unit/test_lancedb_adapter.py` | VALID | Covers active module behavior. |
| `tests/unit/test_level1_action_engine.py` | VALID | Covers active module behavior. |
| `tests/unit/test_level2_action_engine.py` | VALID | Covers active module behavior. |
| `tests/unit/test_level3_action_engine.py` | VALID | Covers active module behavior. |
| `tests/unit/test_phase3c_guards.py` | VALID | Covers active module behavior. |
| `tests/unit/test_ranking_imports.py` | REDUNDANT | Import-smoke checks overlap with broader functional tests. |
| `tests/unit/test_reasoning_contracts.py` | VALID | Covers active module behavior. |
| `tests/unit/test_reasoning_diagnostic.py` | VALID | Covers active module behavior. |
| `tests/unit/test_remediation_layer.py` | VALID | Covers active module behavior. |
| `tests/unit/test_retrieval_imports.py` | REDUNDANT | Import-smoke checks overlap with broader functional tests. |
| `tests/unit/test_scope_injection.py` | VALID | Covers active module behavior. |
| `tests/unit/test_sufficiency_layer.py` | VALID | Covers active module behavior. |
| `tests/unit/test_symbol_resolution.py` | VALID | Covers active module behavior. |
| `tests/unit/test_token_attribution.py` | VALID | Covers active module behavior. |

Summary:
- Valid: 36
- Legacy: 4
- Redundant: 5
- Delete candidate: 0 (none marked without runtime evidence)

## 9. Dependency & Import Sanity Check

- Circular import cycles detected in `src/`: **0**
- High-confidence simplification candidates:
  - `src/homllm/retrieval/pipeline.py`: unused `hashlib` import.
  - `src/homllm/common/config.py`: `Field` import appears unused.
  - `src/homllm/indexer/pipeline.py`: `json` import appears unused.
- Re-export surface inflation: many package `__init__.py` files have no direct importers in static scan; verify before pruning due package import semantics.
- Large orchestration modules that can be split later (not in this pass): `runtime/run_query.py`, `src/homllm/ranking/pipeline.py`, `src/homllm/context/pipeline.py`.

## 10. Cleaning Priority Matrix

| Priority | Item | Risk Level | Cleanup Difficulty | Recommended Action |
|---|---|---|---|---|
| P0 | Unify judge config files and externalize credentials | HIGH | Low | Keep one canonical `eval/judge_config.json`; move key material to ignored secret source and reference via env. |
| P0 | Fix append-only judge duplication behavior | MEDIUM | Low | Add overwrite/replace mode or dedupe by `query_id` on write. |
| P1 | Remove/flag unreachable context budget branch (`preserve_order=False`) | LOW | Low | Mark as legacy or remove after confirming no external caller. |
| P1 | Remove unused context scorer helper signals or re-enable intentionally | MEDIUM | Medium | Either wire `_compute_*` methods into scoring or delete dormant code. |
| P1 | Consolidate root/docs/r2 markdown clutter | LOW | Medium | Archive historical docs into dated folder; keep one canonical architecture report. |
| P1 | Normalize eval directory structure (active vs archive) | LOW | Medium | Split `eval/` into `harness/` and `archive/` subtrees. |
| P2 | Remove duplicate telemetry fields (`mmr_ms`) and dead imports | LOW | Low | Clean retrieval metadata map and stale imports. |
| P2 | Review `LIKELY UNUSED` Python modules (esp. `src/homllm/ranking/dedup.py`) | MEDIUM | Medium | Validate via grep/tests, then archive/remove. |
| P3 | Rationalize overlapping ranking phase2 paths with set optimizer | HIGH | High | Freeze one ranking strategy path and gate/remove alternatives. |

## 11. Do-Not-Modify Zone (During Cleaning)

Core files to avoid touching during hygiene-only cleanup:
- Ranking core: `src/homllm/ranking/pipeline.py`, `src/homllm/ranking/set_optimizer.py`, `src/homllm/ranking/features.py`, `src/homllm/ranking/fusion.py`, `src/homllm/ranking/reranker.py`
- Retrieval backbone: `src/homllm/retrieval/pipeline.py`, `src/homllm/retrieval/hybrid.py`, `src/homllm/retrieval/bm25.py`, `src/homllm/retrieval/vector.py`, `src/homllm/retrieval/granularity_booster.py`
- Context assembly core: `src/homllm/context/pipeline.py`, `src/homllm/context/budget.py`, `src/homllm/context/scorer.py`, `src/homllm/context/stitcher.py`, `src/homllm/context/deduper.py`
- Evaluation harness core: `eval/run_experiment.py`, `eval/run_judge.py`, `runtime/run_query.py`

---

### Audit Integrity Notes
- No new evaluation runs, no API calls, and no runtime logic changes were executed in this forensic pass.
- This report is static-analysis based; items marked likely/legacy should be confirmed before deletion.