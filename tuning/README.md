# Tuning Framework

This directory holds the scaffolding for slow, full-distribution config tuning on top of the
existing `eval/` stack.

The guiding rules are:

- Use the resolved effective config of the current winning profile as the base.
- Keep disabled features disabled unless there is fresh evidence to re-open them.
- Run full 20-query experiments for config comparisons.
- Default evaluation policy: `1` generation run, `2` judge runs, optional `3rd` judge run if the
  first two disagree.
- Only run a second generation pass for shortlisted configs.

## Layout

- `manifests/`
  - Human-edited tuning batches and parameter catalogs.
- `resolved_configs/`
  - Fully materialized runtime configs after YAML + fallback defaults are resolved.
- `generated_configs/`
  - Batch-specific concrete config variants generated from manifests.
- `results/`
  - Batch metadata, judge outputs, summaries.
- `scripts/`
  - Thin orchestration wrappers around the existing `eval/` scripts.

## Workflow

1. Export the resolved winning config.

```powershell
python tuning/scripts/export_resolved_config.py `
  --config configs/analysis/ccg_v2_ab_budget5200_weights_dynamic_budget.yaml
```

2. Edit a manifest under `tuning/manifests/`.

3. Run a tuning batch.

```powershell
python tuning/scripts/run_tuning_batch.py `
  --manifest tuning/manifests/ccg_resolved_search_space.yaml
```

4. Aggregate deterministic experiment summaries.

```powershell
python tuning/scripts/aggregate_tuning_batch.py `
  --batch tuning/results/ccg_resolved_screening_v1/batch_manifest.json
```

## Scope

These scripts are deliberately narrow:

- They reuse `eval/run_experiment.py`.
- They reuse `eval/run_judge.py`.
- They do not replace the existing judge.
- They provide a deterministic system-level summary on top of repeated judge outputs.

## Recommendation

Start with:

- resolved CCG config as the base
- single-parameter sweeps on the highest-leverage controls
- interaction tests only after single-parameter signal appears
