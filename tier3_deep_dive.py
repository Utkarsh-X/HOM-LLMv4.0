"""Deep-dive: token utilization bottleneck, set optimizer, coherence/stitching telemetry."""
import json, os, statistics

RUN_DIR = "eval/runs/tier2.0_validation"

with open(f"{RUN_DIR}/responses.jsonl") as f:
    runs = [json.loads(l) for l in f if l.strip()]

print("=" * 100)
print("DEEP-DIVE 1: TOKEN UTILIZATION BOTTLENECK ANALYSIS")
print("=" * 100)

for i, r in enumerate(runs):
    tp = r.get("telemetry_path", "")
    if not os.path.exists(tp):
        continue
    t = json.load(open(tp))
    ctx = t["phases"].get("CONTEXT", {})
    tokens = ctx.get("tokens", 0)
    budget = ctx.get("token_budget", 0)
    blocks = ctx.get("blocks", 0)
    util = tokens / max(budget, 1) * 100

    # Get the provenance for this query
    run_id = t.get("run_id", "")
    prov_path = os.path.join(os.path.dirname(tp), "provenance.json")
    prov = {}
    if os.path.exists(prov_path):
        prov = json.load(open(prov_path))

    # Check drop_trace for stage counts
    drop_trace = prov.get("context_drop_trace", [])
    kept = sum(1 for d in drop_trace if d.get("drop_reason") == "kept")
    deduped = sum(1 for d in drop_trace if d.get("drop_reason") == "dedup")
    budget_cut = sum(1 for d in drop_trace if d.get("drop_reason") == "budget")
    total_offered = len(drop_trace)

    # Stage counts
    stage_counts = prov.get("stage_counts", {})

    # Coherence telemetry
    coh = prov.get("coherence_refinement", {})

    # Stitching telemetry
    stitch = prov.get("stitching", {})

    if util < 50 or i < 5:  # Show low-util queries and first 5
        print(f"\nQ{i+1:2d}: tokens={tokens:4d}/{budget} util={util:.1f}% blocks={blocks}")
        print(f"  Drop trace: total={total_offered} kept={kept} dedup={deduped} budget={budget_cut}")
        print(f"  Stage counts: {stage_counts}")
        if coh:
            print(f"  Coherence: enabled={coh.get('enabled')} refined={coh.get('blocks_refined')} reorders={coh.get('mid_range_reorders')} max_coh={coh.get('max_coherence','?')} mean_coh={coh.get('mean_coherence','?')}")
            print(f"             same_file_hits={coh.get('same_file_hits')} call_chain_hits={coh.get('call_chain_hits')}")
        if stitch:
            print(f"  Stitching: strategy={stitch.get('grouping_strategy')} imports={stitch.get('import_injection_count')} file_groups={len(stitch.get('file_groups',[]))}")

print("\n" + "=" * 100)
print("DEEP-DIVE 2: SET OPTIMIZER TELEMETRY")
print("=" * 100)

for i, r in enumerate(runs[:5]):
    tp = r.get("telemetry_path", "")
    if not os.path.exists(tp):
        continue
    t = json.load(open(tp))
    rnk = t["phases"].get("RANKING", {})
    so = rnk.get("set_optimization", {})
    geo = rnk.get("ranking_geometry", {})
    print(f"\nQ{i+1}: set_optimization={json.dumps(so, indent=2)[:500]}")
    print(f"      ranking_geometry={json.dumps(geo, indent=2)[:500]}")

print("\n" + "=" * 100)
print("DEEP-DIVE 3: FULL TELEMETRY FILE STRUCTURE (Q1)")
print("=" * 100)

tp0 = runs[0].get("telemetry_path", "")
if os.path.exists(tp0):
    t = json.load(open(tp0))
    # Print all top-level keys
    print(f"Top-level keys: {list(t.keys())}")
    for phase, data in t.get("phases", {}).items():
        if isinstance(data, dict):
            print(f"\n  Phase {phase}: keys={list(data.keys())}")
        else:
            print(f"\n  Phase {phase}: type={type(data)}")

print("\n" + "=" * 100)
print("DEEP-DIVE 4: CANDIDATE TOKEN DISTRIBUTION")
print("=" * 100)

all_block_tokens = []
for r in runs:
    tp = r.get("telemetry_path", "")
    if not os.path.exists(tp):
        continue
    prov_path = os.path.join(os.path.dirname(tp), "provenance.json")
    if os.path.exists(prov_path):
        prov = json.load(open(prov_path))
        drop_trace = prov.get("context_drop_trace", [])
        for d in drop_trace:
            if d.get("drop_reason") == "kept":
                all_block_tokens.append(d.get("estimated_tokens", 0))

if all_block_tokens:
    print(f"Kept block tokens: n={len(all_block_tokens)} mean={statistics.mean(all_block_tokens):.0f} stdev={statistics.stdev(all_block_tokens):.0f} min={min(all_block_tokens)} max={max(all_block_tokens)} p50={sorted(all_block_tokens)[len(all_block_tokens)//2]}")
    # Distribution
    for bucket in [25, 50, 100, 150, 200, 300, 500, 750]:
        count = sum(1 for t in all_block_tokens if t <= bucket and t > (bucket - 25 if bucket <= 50 else bucket // 2))
        print(f"  0-{bucket}: {sum(1 for t in all_block_tokens if t <= bucket)} cumulative")
