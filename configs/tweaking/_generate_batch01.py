from pathlib import Path
import copy
import yaml

root = Path(r'd:\HOM-LLM(v2.0)')
base_path = root / 'tuning' / 'resolved_configs' / 'ccg_v2_ab_budget5200_weights_dynamic_budget.resolved.yaml'
out_dir = root / 'configs' / 'tweaking' / 'ccg_resolved_batch01'
out_dir.mkdir(parents=True, exist_ok=True)

with base_path.open('r', encoding='utf-8') as f:
    base = yaml.safe_load(f)

variants = [
    ('ccg_resolved_baseline', {}, 'Resolved winning CCG config with all fallback defaults materialized.'),
    ('ccg_ret_precision_add2', {'retrieval': {'precision_recovery': {'max_additions': 2}}}, 'Tighten precision recovery breadth by one step.'),
    ('ccg_ret_precision_add4', {'retrieval': {'precision_recovery': {'max_additions': 4}}}, 'Loosen precision recovery breadth by one step.'),
    ('ccg_ret_coverage_add2', {'retrieval': {'coverage_recovery': {'max_additions': 2}}}, 'Reduce coverage recovery insertions.'),
    ('ccg_ret_coverage_add4', {'retrieval': {'coverage_recovery': {'max_additions': 4}}}, 'Increase coverage recovery insertions.'),
    ('ccg_ret_postmerge_40', {'retrieval': {'post_merge_candidates': 40}}, 'Smaller post-merge candidate surface.'),
    ('ccg_ret_postmerge_60', {'retrieval': {'post_merge_candidates': 60}}, 'Larger post-merge candidate surface.'),
    ('ccg_ctx_dynstep_300', {'context': {'dynamic_budget_step_tokens': 300}}, 'Smaller dynamic budget expansion step.'),
    ('ccg_ctx_dynstep_500', {'context': {'dynamic_budget_step_tokens': 500}}, 'Larger dynamic budget expansion step.'),
    ('ccg_ctx_dynexp_1', {'context': {'dynamic_budget_max_expansions': 1}}, 'More conservative dynamic expansion count.'),
    ('ccg_ctx_dynexp_3', {'context': {'dynamic_budget_max_expansions': 3}}, 'More aggressive dynamic expansion count.'),
    ('ccg_ctx_relgate_020', {'context': {'relevance_gate_threshold': 0.20}}, 'Loosen relevance gate to admit more blocks.'),
    ('ccg_ctx_relgate_030', {'context': {'relevance_gate_threshold': 0.30}}, 'Tighten relevance gate to reject weaker blocks.'),
    ('ccg_ctx_graph_015', {'context': {'submodular': {'w_rrf': 0.60, 'w_graph': 0.15}}}, 'Reduce graph bias, return weight to RRF.'),
    ('ccg_ctx_graph_025', {'context': {'submodular': {'w_rrf': 0.50, 'w_graph': 0.25}}}, 'Increase graph bias, reduce RRF slightly.'),
    ('ccg_rank_bm25rescue_10', {'ranking': {'reranker': {'bm25_rescue_top_k': 10}}}, 'Reduce BM25 rescue set for reranker.'),
    ('ccg_rank_bm25rescue_20', {'ranking': {'reranker': {'bm25_rescue_top_k': 20}}}, 'Increase BM25 rescue set for reranker.'),
]

def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst

index = []
for name, overrides, rationale in variants:
    payload = copy.deepcopy(base)
    deep_merge(payload, overrides)
    path = out_dir / f'{name}.yaml'
    with path.open('w', encoding='utf-8') as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=False)
    index.append({'name': name, 'file': path.name, 'rationale': rationale, 'overrides': overrides})

index_payload = {'base_config': str(base_path.relative_to(root)).replace('\\', '/'), 'variants': index}
with (out_dir / 'variant_index.yaml').open('w', encoding='utf-8') as f:
    yaml.safe_dump(index_payload, f, sort_keys=False, allow_unicode=False)

lines = []
lines.append('# Manual Runbook')
lines.append('')
lines.append('Base directory: `configs/tweaking/ccg_resolved_batch01`')
lines.append('')
lines.append('Each variant gets:')
lines.append('- 1 experiment run')
lines.append('- 1 Gemini judge run')
lines.append('- 1 Cerebras SDK judge run')
lines.append('')
for item in index:
    name = item['name']
    cfg_rel = f"configs/tweaking/ccg_resolved_batch01/{item['file']}"
    lines.append(f'## {name}')
    lines.append(f"Rationale: {item['rationale']}")
    lines.append('')
    lines.append('```powershell')
    lines.append(f"python eval/run_experiment.py --select 1-20 --config {cfg_rel} --run-name {name} --telemetry-print")
    lines.append(f"python eval/run_judge.py --responses eval/runs/{name}/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/{name}/judge_results__gemini_manual.jsonl")
    lines.append(f"python eval/run_judge.py --responses eval/runs/{name}/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/{name}/judge_results__cerebras_manual.jsonl")
    lines.append('```')
    lines.append('')

(out_dir / 'MANUAL_RUNBOOK.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Wrote {len(index)} variants to {out_dir}')
