"""Extract detailed Tier 2 telemetry for Tier 3 analysis."""
import json, os, statistics

RUN_DIR = "eval/runs/tier2.0_validation"

with open(f"{RUN_DIR}/responses.jsonl") as f:
    runs = [json.loads(l) for l in f if l.strip()]

print("=" * 120)
print("TIER 2 DETAILED TELEMETRY BREAKDOWN")
print("=" * 120)

# Per-query breakdown
for i, r in enumerate(runs):
    tp = r.get("telemetry_path", "")
    if not os.path.exists(tp):
        continue
    t = json.load(open(tp))
    ret = t["phases"].get("RETRIEVAL", {})
    rnk = t["phases"].get("RANKING", {})
    ctx = t["phases"].get("CONTEXT", {})
    cqi = t["phases"].get("CQI_MONITOR", {})
    sp = rnk.get("signal_profile", {})
    so = rnk.get("set_optimization", {})
    geo = rnk.get("ranking_geometry", {})
    ax = cqi.get("axis_detail", {})
    contr = cqi.get("contributions", {})
    
    print(f"\nQ{i+1:2d}: {r.get('query','')[:80]}")
    print(f"  RETRIEVAL: cands={ret.get('candidates',0)} bm25={ret.get('bm25_count',0)} vec={ret.get('vector_count',0)}")
    print(f"  RANKING:   reranker={rnk.get('reranker',False)} alpha={geo.get('rerank_alpha','?')} struct_gamma={geo.get('struct_gamma','?')}")
    print(f"             margin={sp.get('margin',0):.4f} entropy={sp.get('file_entropy',0):.4f} concentration={rnk.get('ranking_concentration',{})}")
    print(f"  SET_OPT:   enabled={so.get('enabled','?')} obj={so.get('objective_score','?')} redundancy={so.get('redundancy','?')}")
    print(f"  CONTEXT:   blocks={ctx.get('blocks',0)} tokens={ctx.get('tokens',0)}/{ctx.get('token_budget',0)} util={ctx.get('tokens',0)/max(ctx.get('token_budget',1),1)*100:.1f}%")
    print(f"  CQI:       cqi4={cqi.get('cqi4',0):.4f} CI={cqi.get('coherence_index',0):.4f} RCI={cqi.get('ranking_confidence_index',0):.4f} zone={cqi.get('zone','?')}")
    if ax:
        print(f"  AXIS:      M3_pct={ax.get('M3_percentile',0):.4f} M4_pct={ax.get('M4_percentile',0):.4f} M5_pct={ax.get('M5_percentile',0):.4f} M6_pct={ax.get('M6_percentile',0):.4f}")
    if contr:
        print(f"  CONTRIB:   {contr}")
    print(f"  TOP/BOT:   top={cqi.get('top_contributor','?')} bot={cqi.get('bottom_contributor','?')}")

# Aggregate statistics
print("\n" + "=" * 120)
print("AGGREGATE STATISTICS")
print("=" * 120)

all_cands, all_blocks, all_tokens, all_budgets = [], [], [], []
all_margins, all_entropies, all_cqis = [], [], []
all_ci, all_rci = [], []
all_m3p, all_m4p, all_m5p, all_m6p = [], [], [], []
all_alphas = []
reranker_count = 0

for r in runs:
    tp = r.get("telemetry_path", "")
    if not os.path.exists(tp):
        continue
    t = json.load(open(tp))
    ret = t["phases"].get("RETRIEVAL", {})
    rnk = t["phases"].get("RANKING", {})
    ctx = t["phases"].get("CONTEXT", {})
    cqi = t["phases"].get("CQI_MONITOR", {})
    sp = rnk.get("signal_profile", {})
    geo = rnk.get("ranking_geometry", {})
    ax = cqi.get("axis_detail", {})
    
    all_cands.append(ret.get("candidates", 0))
    all_blocks.append(ctx.get("blocks", 0))
    all_tokens.append(ctx.get("tokens", 0))
    all_budgets.append(ctx.get("token_budget", 0))
    all_margins.append(sp.get("margin", 0))
    all_entropies.append(sp.get("file_entropy", 0))
    all_cqis.append(cqi.get("cqi4", 0))
    all_ci.append(cqi.get("coherence_index", 0))
    all_rci.append(cqi.get("ranking_confidence_index", 0))
    if ax:
        all_m3p.append(ax.get("M3_percentile", 0))
        all_m4p.append(ax.get("M4_percentile", 0))
        all_m5p.append(ax.get("M5_percentile", 0))
        all_m6p.append(ax.get("M6_percentile", 0))
    if geo.get("rerank_alpha"):
        all_alphas.append(float(geo["rerank_alpha"]))
    if rnk.get("reranker"):
        reranker_count += 1

def pstat(name, vals):
    if not vals:
        print(f"  {name}: NO DATA")
        return
    print(f"  {name}: mean={statistics.mean(vals):.4f} stdev={statistics.stdev(vals):.4f} min={min(vals):.4f} max={max(vals):.4f}")

print(f"\nReranker activation: {reranker_count}/{len(runs)}")
pstat("Candidates", [float(x) for x in all_cands])
pstat("Blocks", [float(x) for x in all_blocks])
pstat("Tokens", [float(x) for x in all_tokens])
pstat("Budget", [float(x) for x in all_budgets])
pstat("Token util%", [t/max(b,1)*100 for t,b in zip(all_tokens, all_budgets)])
pstat("CQI4", all_cqis)
pstat("CI", all_ci)
pstat("RCI", all_rci)
pstat("M3 (entropy)", all_entropies)
pstat("M5 (margin)", all_margins)
pstat("Alpha", all_alphas)
if all_m3p:
    pstat("M3_percentile", all_m3p)
    pstat("M4_percentile", all_m4p)
    pstat("M5_percentile", all_m5p)
    pstat("M6_percentile", all_m6p)

# Token utilization distribution
print(f"\nToken utilization distribution:")
for bucket in [20, 30, 40, 50, 60, 70, 80, 90, 100]:
    count = sum(1 for t,b in zip(all_tokens, all_budgets) if t/max(b,1)*100 <= bucket and t/max(b,1)*100 > bucket-10)
    print(f"  {bucket-10}-{bucket}%: {'#'*count} ({count})")
