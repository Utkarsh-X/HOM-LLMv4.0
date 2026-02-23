"""Extract Tier 2 validation metrics and compare against Tier 1 baseline."""
import json, os, statistics

RUN_DIR = "eval/runs/tier2.0_validation"

with open(f"{RUN_DIR}/responses.jsonl") as f:
    runs = [json.loads(l) for l in f if l.strip()]

cqis, m3s, m4s, m5s, tokens, latencies = [], [], [], [], [], []
coherence_hits, call_chain_hits = [], []
stitch_imports = []

for r in runs:
    tp = r.get("telemetry_path", "")
    latencies.append(r["latency_ms"])
    if os.path.exists(tp):
        with open(tp) as tf:
            t = json.load(tf)
        ctx = t["phases"].get("CONTEXT", {})
        cqi = t["phases"].get("CQI_MONITOR", {})
        rnk = t["phases"].get("RANKING", {})
        sp = rnk.get("signal_profile", {})
        so = rnk.get("set_optimization", {})
        cqis.append(cqi.get("cqi4", 0))
        m3s.append(sp.get("file_entropy", 0))
        m4s.append(so.get("redundancy", 0))
        m5s.append(sp.get("margin", 0))
        tokens.append(ctx.get("tokens", 0))

        # Tier 2 specific: axis_detail
        axis = cqi.get("axis_detail", {})

        # Coherence refinement telemetry (from provenance inside drop_trace parent)
        # Check if coherence_refinement is in CONTEXT phase
        cr = ctx.get("coherence_refinement")
        if not cr:
            # Try from provenance in the run artifacts
            pass

print("=" * 60)
print("TIER 2.0 VALIDATION METRICS")
print("=" * 60)
print(f"Queries: {len(runs)}")
print()
print(f"Context tokens: mean={statistics.mean(tokens):.0f}, stdev={statistics.stdev(tokens):.0f}")
print(f"                min={min(tokens)}, max={max(tokens)}")
print(f"Token budget: 3600  utilization: {statistics.mean(tokens)/3600*100:.1f}%")
print()
print(f"CQI4: mean={statistics.mean(cqis):.4f}, stdev={statistics.stdev(cqis):.4f}")
print(f"       min={min(cqis):.4f}, max={max(cqis):.4f}")
zones = {
    "poor": sum(1 for c in cqis if c < 0.3),
    "neutral": sum(1 for c in cqis if 0.3 <= c < 0.5),
    "good": sum(1 for c in cqis if 0.5 <= c < 0.7),
    "excellent": sum(1 for c in cqis if c >= 0.7),
}
print(f"CQI distribution: {zones}")
print()
print(f"M3 (file_entropy): mean={statistics.mean(m3s):.4f}, stdev={statistics.stdev(m3s):.4f}")
print(f"M4 (redundancy):   mean={statistics.mean(m4s):.4f}, stdev={statistics.stdev(m4s):.4f}")
print(f"M5 (margin):       mean={statistics.mean(m5s):.4f}, stdev={statistics.stdev(m5s):.4f}")
print()
print(f"Latency: mean={statistics.mean(latencies):.0f}ms, stdev={statistics.stdev(latencies):.0f}ms")
print(f"         min={min(latencies):.0f}ms, max={max(latencies):.0f}ms")
print()

# Tier 1 baseline comparison
T1_CQI = 0.6275
T1_M3 = 0.8567
T1_M4 = 0.0000
T1_M5 = 0.0935
T1_TOKENS = 1470
T1_LATENCY = 21495

print("=" * 60)
print("TIER 1 vs TIER 2 COMPARISON")
print("=" * 60)
print(f"{'Metric':<22} {'Tier 1':>10} {'Tier 2':>10} {'Delta':>10} {'Status':>8}")
print("-" * 60)

def status(val, baseline, better="higher"):
    if better == "higher":
        return "UP" if val > baseline * 1.01 else ("==" if abs(val - baseline) < baseline * 0.01 else "DOWN")
    elif better == "lower":
        return "UP" if val < baseline * 0.99 else ("==" if abs(val - baseline) < baseline * 0.01 else "DOWN")
    else:
        return "STABLE" if abs(val - baseline) < baseline * 0.05 else "SHIFTED"

cqi_mean = statistics.mean(cqis)
m3_mean = statistics.mean(m3s)
m4_mean = statistics.mean(m4s)
m5_mean = statistics.mean(m5s)
tok_mean = statistics.mean(tokens)
lat_mean = statistics.mean(latencies)

print(f"{'CQI4 mean':<22} {T1_CQI:>10.4f} {cqi_mean:>10.4f} {cqi_mean-T1_CQI:>+10.4f} {status(cqi_mean, T1_CQI, 'higher'):>8}")
print(f"{'M3 (file_entropy)':<22} {T1_M3:>10.4f} {m3_mean:>10.4f} {m3_mean-T1_M3:>+10.4f} {status(m3_mean, T1_M3, 'stable'):>8}")
print(f"{'M4 (redundancy)':<22} {T1_M4:>10.4f} {m4_mean:>10.4f} {m4_mean-T1_M4:>+10.4f} {status(m4_mean, T1_M4, 'lower'):>8}")
print(f"{'M5 (margin)':<22} {T1_M5:>10.4f} {m5_mean:>10.4f} {m5_mean-T1_M5:>+10.4f} {status(m5_mean, T1_M5, 'higher'):>8}")
print(f"{'Context tokens':<22} {T1_TOKENS:>10.0f} {tok_mean:>10.0f} {tok_mean-T1_TOKENS:>+10.0f} {'MORE' if tok_mean > T1_TOKENS else 'LESS':>8}")
print(f"{'Latency (ms)':<22} {T1_LATENCY:>10.0f} {lat_mean:>10.0f} {lat_mean-T1_LATENCY:>+10.0f} {status(lat_mean, T1_LATENCY, 'lower'):>8}")
print()

# Per-query CQI
print("Per-query CQI4:")
for i, c in enumerate(cqis, 1):
    print(f"  Q{i:2d}: {c:.4f}")
