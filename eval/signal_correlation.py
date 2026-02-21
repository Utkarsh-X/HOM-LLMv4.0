"""
Context Signal Correlation Analysis.

Computes context quality metrics from existing eval run telemetry
and correlates them with LLM judge outcomes.

Usage:
    python eval/signal_correlation.py

Output: Correlation table printed to stdout + saved to eval/runs/<run>/correlation_report.md
"""

import json
import math
import os
import sys
from pathlib import Path
from statistics import mean, stdev

# ──────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────

RUN_DIR = Path(r"d:\HOM-LLM(v2.0)\eval\runs\run_20260219_184016")
JUDGE_FILE = "judge_results__gpt-oss-120b.jsonl"
RESPONSES_FILE = "responses.jsonl"

# Judge dimensions to correlate against
JUDGE_DIMS = [
    "overall_quality",
    "semantic_correctness",
    "factual_consistency",
    "completeness",
    "hallucination_risk",
]


# ──────────────────────────────────────────────────────────────────────────
# METRIC COMPUTATION (from telemetry — no pipeline objects needed)
# ──────────────────────────────────────────────────────────────────────────

def compute_m1_semantic_strength(telemetry: dict) -> float:
    """M1: Mean semantic_score of kept context blocks."""
    drop_trace = telemetry["phases"]["CONTEXT"]["drop_trace"]
    kept = [b for b in drop_trace if b.get("drop_reason") == "kept"]
    if not kept:
        return 0.0
    scores = [b["semantic_score"] for b in kept]
    return sum(scores) / len(scores)


def compute_m3_file_entropy(telemetry: dict) -> float:
    """M3: Normalized Shannon entropy of file distribution in kept blocks."""
    drop_trace = telemetry["phases"]["CONTEXT"]["drop_trace"]
    kept = [b for b in drop_trace if b.get("drop_reason") == "kept"]
    if not kept:
        return 0.0

    files = [b["file"] for b in kept]
    k = len(files)
    from collections import Counter
    counts = Counter(files)
    unique = len(counts)

    if unique <= 1:
        return 0.0

    h = 0.0
    for count in counts.values():
        p = count / k
        if p > 0:
            h -= p * math.log(p)

    h_max = math.log(unique)
    return h / h_max if h_max > 0 else 0.0


def compute_m5_score_separation(telemetry: dict) -> float:
    """M5: Coefficient of variation of final_score across ALL candidates."""
    drop_trace = telemetry["phases"]["CONTEXT"]["drop_trace"]
    if not drop_trace:
        return 0.0
    scores = [b["final_score"] for b in drop_trace]
    n = len(scores)
    mu = sum(scores) / n
    if abs(mu) < 1e-10:
        return 0.0
    variance = sum((s - mu) ** 2 for s in scores) / n
    sigma = math.sqrt(variance)
    return sigma / abs(mu)


def compute_m6_reranker_influence(telemetry: dict) -> float:
    """M6: From ranking_geometry telemetry (full ranked surface)."""
    geometry = telemetry["phases"]["RANKING"].get("ranking_geometry")
    if geometry and "rerank_contribution_percent" in geometry:
        return float(geometry["rerank_contribution_percent"]) / 100.0
    return 0.0


def compute_m7_budget_utilization(telemetry: dict) -> float:
    """M7: used_tokens / token_budget."""
    ctx = telemetry["phases"]["CONTEXT"]
    budget = ctx.get("token_budget", 0)
    used = ctx.get("tokens", 0)
    if budget <= 0:
        return 0.0
    return used / budget


def compute_metrics(telemetry: dict) -> dict[str, float]:
    """Compute all available metrics from telemetry."""
    return {
        "M1_semantic_strength": compute_m1_semantic_strength(telemetry),
        "M3_file_entropy": compute_m3_file_entropy(telemetry),
        "M5_score_separation": compute_m5_score_separation(telemetry),
        "M6_reranker_influence": compute_m6_reranker_influence(telemetry),
        "M7_budget_utilization": compute_m7_budget_utilization(telemetry),
    }


# ──────────────────────────────────────────────────────────────────────────
# CORRELATION FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────

def pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient. Returns 0.0 on degenerate input."""
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / n)
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / n)
    if sx < 1e-15 or sy < 1e-15:
        return 0.0
    return cov / (sx * sy)


def spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation. Returns 0.0 on degenerate input."""
    n = len(x)
    if n < 3:
        return 0.0

    def _rank(vals):
        indexed = sorted(enumerate(vals), key=lambda t: t[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = _rank(x)
    ry = _rank(y)
    return pearson(rx, ry)


# ──────────────────────────────────────────────────────────────────────────
# Z-SCORE COMPOSITE
# ──────────────────────────────────────────────────────────────────────────

def zscore_normalize(values: list[float]) -> list[float]:
    """Z-score normalize a list. Returns zeros if std is near-zero."""
    n = len(values)
    if n < 2:
        return [0.0] * n
    mu = sum(values) / n
    s = math.sqrt(sum((v - mu) ** 2 for v in values) / (n - 1))  # sample std
    if s < 1e-15:
        return [0.0] * n
    return [(v - mu) / s for v in values]


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    # 1. Load responses (for telemetry_path and query_text)
    responses = []
    with open(RUN_DIR / RESPONSES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            responses.append(json.loads(line.strip()))

    # 2. Load judge results
    judge_results = {}
    with open(RUN_DIR / JUDGE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            j = json.loads(line.strip())
            judge_results[j["query_id"]] = j

    # 3. For each query: load telemetry → compute metrics → join with judge
    rows = []
    for resp in responses:
        qid = resp["query_id"]
        tpath = resp["telemetry_path"]

        # Load telemetry
        if not os.path.exists(tpath):
            print(f"WARN: telemetry missing for q{qid}: {tpath}", file=sys.stderr)
            continue

        telemetry = json.load(open(tpath, "r", encoding="utf-8"))
        metrics = compute_metrics(telemetry)

        # Join with judge
        if qid not in judge_results:
            print(f"WARN: no judge result for q{qid}", file=sys.stderr)
            continue

        judge = judge_results[qid]
        scores = judge["scores"]

        # Compute judge deltas (candidate - baseline)
        deltas = {}
        for dim in JUDGE_DIMS:
            if dim in scores:
                deltas[dim] = scores[dim]["candidate"] - scores[dim]["baseline"]

        rows.append({
            "query_id": qid,
            "query_text": resp["query_text"][:60],
            **metrics,
            **{f"delta_{d}": v for d, v in deltas.items()},
        })

    if not rows:
        print("ERROR: No data rows generated.", file=sys.stderr)
        return

    n = len(rows)
    print(f"\n{'='*80}")
    print(f"CONTEXT SIGNAL CORRELATION ANALYSIS")
    print(f"Run: {RUN_DIR.name}")
    print(f"Judge: {JUDGE_FILE}")
    print(f"Queries: {n}")
    print(f"{'='*80}\n")

    # 4. Print raw data table
    metric_names = ["M1_semantic_strength", "M3_file_entropy", "M5_score_separation",
                    "M6_reranker_influence", "M7_budget_utilization"]
    delta_names = [f"delta_{d}" for d in JUDGE_DIMS]

    print("─── RAW DATA ───")
    header = f"{'qid':>4} " + " ".join(f"{m:>12}" for m in metric_names)
    header += " " + " ".join(f"{d:>16}" for d in delta_names)
    print(header)
    for row in rows:
        line = f"{row['query_id']:>4} "
        line += " ".join(f"{row[m]:>12.4f}" for m in metric_names)
        line += " " + " ".join(f"{row.get(d, 0):>16.1f}" for d in delta_names)
        print(line)

    # 5. Compute correlations
    print(f"\n─── CORRELATIONS (n={n}) ───")

    # Note about small sample size
    if n < 10:
        print(f"\n⚠️  WARNING: n={n} is very small. Correlations may be unreliable.")
        print(f"   Minimum recommended: n≥20 for meaningful correlations.\n")

    results = []
    for metric in metric_names:
        m_vals = [row[metric] for row in rows]
        for dim in JUDGE_DIMS:
            delta_key = f"delta_{dim}"
            d_vals = [row.get(delta_key, 0) for row in rows]
            p = pearson(m_vals, d_vals)
            s = spearman(m_vals, d_vals)
            results.append({
                "metric": metric,
                "judge_dim": dim,
                "pearson": p,
                "spearman": s,
                "abs_pearson": abs(p),
            })

    # Sort by |pearson| descending
    results.sort(key=lambda r: r["abs_pearson"], reverse=True)

    # Print correlation table
    print(f"\n{'Metric':<25} {'Judge Dimension':<25} {'Pearson':>8} {'Spearman':>9} {'Signal':>10}")
    print("─" * 80)
    for r in results:
        ap = r["abs_pearson"]
        if ap >= 0.5:
            signal = "🟢 STRONG"
        elif ap >= 0.35:
            signal = "🟡 MODERATE"
        elif ap >= 0.2:
            signal = "⚪ WEAK"
        else:
            signal = "❌ NONE"

        print(f"{r['metric']:<25} {r['judge_dim']:<25} {r['pearson']:>+8.3f} {r['spearman']:>+9.3f} {signal:>10}")

    # 6. Composite simple (z-score sum, no weights)
    print(f"\n─── COMPOSITE ANALYSIS ───")

    # Z-score normalize each metric across queries
    zscored = {}
    for metric in metric_names:
        vals = [row[metric] for row in rows]
        zscored[metric] = zscore_normalize(vals)

    # Composite = sum of z-scores
    composite_vals = []
    for i in range(n):
        c = sum(zscored[m][i] for m in metric_names)
        composite_vals.append(c)

    for dim in JUDGE_DIMS:
        delta_key = f"delta_{dim}"
        d_vals = [row.get(delta_key, 0) for row in rows]
        p = pearson(composite_vals, d_vals)
        s = spearman(composite_vals, d_vals)
        ap = abs(p)
        if ap >= 0.5:
            signal = "🟢 STRONG"
        elif ap >= 0.35:
            signal = "🟡 MODERATE"
        elif ap >= 0.2:
            signal = "⚪ WEAK"
        else:
            signal = "❌ NONE"
        print(f"composite_simple × {dim:<25} Pearson={p:>+.3f} Spearman={s:>+.3f} {signal}")

    # 7. Summary
    print(f"\n─── SUMMARY ───")
    strong = [r for r in results if r["abs_pearson"] >= 0.5]
    moderate = [r for r in results if 0.35 <= r["abs_pearson"] < 0.5]
    weak = [r for r in results if r["abs_pearson"] < 0.2]

    if strong:
        print(f"\n🟢 STRONG SIGNALS ({len(strong)}):")
        for r in strong:
            direction = "positive" if r["pearson"] > 0 else "NEGATIVE"
            print(f"   {r['metric']} × {r['judge_dim']}: r={r['pearson']:+.3f} ({direction})")

    if moderate:
        print(f"\n🟡 MODERATE SIGNALS ({len(moderate)}):")
        for r in moderate:
            direction = "positive" if r["pearson"] > 0 else "NEGATIVE"
            print(f"   {r['metric']} × {r['judge_dim']}: r={r['pearson']:+.3f} ({direction})")

    total_near_zero = len([r for r in results if r["abs_pearson"] < 0.15])
    print(f"\n❌ Near-zero correlations: {total_near_zero}/{len(results)}")

    # 8. Metrics NOT computed
    print(f"\n─── NOT COMPUTED ───")
    print(f"   M2 (query_term_recall): Block content not in telemetry (codebase not available)")
    print(f"   M4 (content_overlap):   Block content not in telemetry (codebase not available)")

    # 9. Verdict
    print(f"\n{'='*80}")
    max_r = max(r["abs_pearson"] for r in results) if results else 0.0
    if max_r >= 0.5:
        print(f"VERDICT: Case A — Strong predictive signal found (max |r| = {max_r:.3f})")
        print(f"         Pre-generation gating is feasible.")
    elif max_r >= 0.35:
        print(f"VERDICT: Case B — Moderate mixed signals (max |r| = {max_r:.3f})")
        print(f"         Refine top predictive metrics.")
    else:
        print(f"VERDICT: Case C — Weak correlation (max |r| = {max_r:.3f})")
        print(f"         Kernel measures structural quality, not answer sufficiency.")
        print(f"         Design sufficiency metrics (layer 2).")
    print(f"{'='*80}")

    # 10. Per-metric descriptive stats
    print(f"\n─── METRIC DESCRIPTIVE STATISTICS ───")
    for metric in metric_names:
        vals = [row[metric] for row in rows]
        mn = min(vals)
        mx = max(vals)
        avg = sum(vals) / len(vals)
        s = math.sqrt(sum((v - avg)**2 for v in vals) / len(vals)) if len(vals) > 1 else 0.0
        print(f"   {metric:<25} min={mn:.4f} max={mx:.4f} mean={avg:.4f} std={s:.4f}")


if __name__ == "__main__":
    main()
