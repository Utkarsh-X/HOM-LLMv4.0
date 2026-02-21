"""
Composite Context Quality Index (CQI) — Predictive Analysis.

Builds a weighted standardized composite from M4, M5, M3(neg), M6, M1.
Validates against judge overall_quality delta and win/loss.
Measures precision/recall for regression prediction.

Usage:
    set PYTHONIOENCODING=utf-8
    python eval/cqi_analysis.py --run <run_name>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

# Reuse metric computation from the correlation script
from signal_correlation_base20 import (
    compute_all_metrics,
    JUDGE_DIMS,
    RUNS_DIR,
    EVAL_DIR,
    find_latest_run,
    find_judge_file,
    load_responses,
    load_judge,
    pearson,
    spearman,
    bootstrap_ci,
    BOOTSTRAP_SEED,
)


# ──────────────────────────────────────────────────────────────────────────
# CQI WEIGHTS — derived from absolute correlation magnitudes with
# overall_quality, weighted by stability (1/LOO_std).
# M3 gets negative sign (higher entropy → worse quality).
# ──────────────────────────────────────────────────────────────────────────

# Raw |r| with overall_quality from 7-metric run:
# M5: 0.520, M4: 0.421, M6: 0.389, M3: 0.308 (neg), M1: 0.141
# Using these as raw weights, then normalizing to sum=1.
# M2 (0.168) and M7 (0.100) excluded — near-zero signal.

RAW_WEIGHTS = {
    "M4_content_overlap":    0.502,   # Strongest on factual_consistency
    "M5_score_separation":   0.520,   # Strongest on overall_quality
    "M3_file_entropy":      -0.403,   # Negative (more entropy → worse)
    "M6_reranker_influence":  0.389,
    "M1_semantic_strength":   0.369,
}

# Normalize absolute values to sum to 1
_abs_sum = sum(abs(v) for v in RAW_WEIGHTS.values())
CQI_WEIGHTS = {k: v / _abs_sum for k, v in RAW_WEIGHTS.items()}


def compute_cqi(metrics: dict[str, float], 
                means: dict[str, float], 
                stds: dict[str, float]) -> float:
    """Compute CQI from metric values using z-score standardization + weights.
    
    CQI = Σ (w_i × z_i) where z_i = (x_i - μ_i) / σ_i
    Then rescaled to [0, 1] via sigmoid.
    """
    z_sum = 0.0
    for metric, weight in CQI_WEIGHTS.items():
        val = metrics.get(metric, 0.0)
        if val is None:
            val = 0.0
        std = stds.get(metric, 1.0)
        if std < 1e-10:
            std = 1.0
        z = (val - means.get(metric, 0.0)) / std
        z_sum += weight * z
    
    # Sigmoid rescale to [0, 1]
    return 1.0 / (1.0 + math.exp(-z_sum))


def precision_recall_at_threshold(cqi_values: list[float],
                                   wins: list[bool],
                                   threshold: float) -> dict:
    """Compute precision/recall for predicting GOOD outcomes (win=True) 
    when CQI >= threshold, and regression when CQI < threshold."""
    
    # Predict good when CQI >= threshold
    tp = sum(1 for c, w in zip(cqi_values, wins) if c >= threshold and w)
    fp = sum(1 for c, w in zip(cqi_values, wins) if c >= threshold and not w)
    fn = sum(1 for c, w in zip(cqi_values, wins) if c < threshold and w)
    tn = sum(1 for c, w in zip(cqi_values, wins) if c < threshold and not w)
    
    precision_good = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall_good = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    # Regression prediction: CQI < threshold → predict regression
    precision_reg = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    recall_reg = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    
    f1_good = 2 * precision_good * recall_good / (precision_good + recall_good) if (precision_good + recall_good) > 0 else 0.0
    f1_reg = 2 * precision_reg * recall_reg / (precision_reg + recall_reg) if (precision_reg + recall_reg) > 0 else 0.0
    
    return {
        "threshold": threshold,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision_good": precision_good,
        "recall_good": recall_good,
        "f1_good": f1_good,
        "precision_reg": precision_reg,
        "recall_reg": recall_reg,
        "f1_reg": f1_reg,
        "accuracy": (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="CQI — Composite Context Quality Index analysis")
    parser.add_argument("--run", type=str, help="Run name (default: latest)")
    parser.add_argument("--judge-file", type=str, help="Judge results filename override")
    args = parser.parse_args()

    # Resolve run
    run_dir = RUNS_DIR / args.run if args.run else find_latest_run()
    if not run_dir.exists():
        print(f"ERROR: {run_dir}", file=sys.stderr)
        sys.exit(1)

    judge_path = run_dir / args.judge_file if args.judge_file else find_judge_file(run_dir)
    responses = load_responses(run_dir)
    judge_results = load_judge(judge_path)

    # Load all metrics
    rows = []
    for resp in responses:
        qid = resp["query_id"]
        tpath = resp.get("telemetry_path", "")
        if not tpath or not os.path.exists(tpath):
            continue
        telemetry = json.load(open(tpath, "r", encoding="utf-8"))
        metrics = compute_all_metrics(telemetry, query_text=resp.get("query_text", ""))
        if qid not in judge_results:
            continue
        scores = judge_results[qid]["scores"]
        deltas = {}
        for dim in JUDGE_DIMS:
            if dim in scores:
                deltas[dim] = scores[dim]["candidate"] - scores[dim]["baseline"]
        
        # Win = improved overall_quality delta > 0
        overall_delta = deltas.get("overall_quality", 0)
        win = overall_delta > 0
        
        row = {
            "query_id": qid,
            "query_text": resp.get("query_text", "")[:60],
            "win": win,
            "overall_delta": overall_delta,
            **{k: (v if v is not None else 0.0) for k, v in metrics.items()},
            **{f"delta_{d}": v for d, v in deltas.items()},
        }
        rows.append(row)

    n = len(rows)
    if n < 4:
        print(f"ERROR: Only {n} rows", file=sys.stderr)
        sys.exit(1)

    # Compute means/stds for z-score
    metric_names = list(CQI_WEIGHTS.keys())
    means = {}
    stds = {}
    for m in metric_names:
        vals = [r[m] for r in rows]
        mu = sum(vals) / n
        means[m] = mu
        stds[m] = math.sqrt(sum((v - mu) ** 2 for v in vals) / n)

    # Compute CQI for each query
    for row in rows:
        row["cqi"] = compute_cqi(row, means, stds)

    # Sort by CQI descending
    rows.sort(key=lambda r: r["cqi"], reverse=True)

    out = sys.stdout
    W = 90

    # ──────────────────────────────────────────────────────────────────
    # REPORT
    # ──────────────────────────────────────────────────────────────────

    out.write("\n" + "=" * W + "\n")
    out.write("COMPOSITE CONTEXT QUALITY INDEX (CQI) — PREDICTIVE ANALYSIS\n")
    out.write(f"Run: {run_dir.name} | Queries: {n}\n")
    out.write("=" * W + "\n\n")

    # WEIGHTS
    out.write("--- CQI WEIGHTS (normalized from correlation magnitudes) ---\n")
    for m, w in sorted(CQI_WEIGHTS.items(), key=lambda x: abs(x[1]), reverse=True):
        sign = "+" if w > 0 else ""
        out.write(f"  {m:<25} {sign}{w:.4f}\n")
    out.write(f"\n  Formula: CQI = sigmoid(Σ w_i × z_i), z_i = (x_i - μ_i) / σ_i\n\n")

    # PER-QUERY TABLE
    out.write("--- CQI PER QUERY (sorted by CQI, descending) ---\n")
    out.write(f"{'Rank':>4} {'CQI':>6} {'Win':>4} {'ΔOQ':>5} {'Query':>60}\n")
    out.write("-" * W + "\n")
    n_wins = 0
    n_losses = 0
    for i, row in enumerate(rows):
        win_str = " ✓" if row["win"] else " ✗"
        out.write(f"{i+1:>4} {row['cqi']:>6.3f} {win_str:>4} {row['overall_delta']:>+5.0f} {row['query_text']:>60}\n")
        if row["win"]:
            n_wins += 1
        else:
            n_losses += 1

    out.write(f"\n  Total: {n_wins} wins, {n_losses} losses\n")

    # CQI DISTRIBUTION
    cqi_vals = [r["cqi"] for r in rows]
    cqi_mean = sum(cqi_vals) / n
    cqi_std = math.sqrt(sum((c - cqi_mean) ** 2 for c in cqi_vals) / n)
    cqi_min, cqi_max = min(cqi_vals), max(cqi_vals)
    
    win_cqis = [r["cqi"] for r in rows if r["win"]]
    loss_cqis = [r["cqi"] for r in rows if not r["win"]]
    
    out.write(f"\n--- CQI DISTRIBUTION ---\n")
    out.write(f"  All:    mean={cqi_mean:.3f} std={cqi_std:.3f} min={cqi_min:.3f} max={cqi_max:.3f}\n")
    if win_cqis:
        out.write(f"  Wins:   mean={sum(win_cqis)/len(win_cqis):.3f} n={len(win_cqis)}\n")
    if loss_cqis:    
        out.write(f"  Losses: mean={sum(loss_cqis)/len(loss_cqis):.3f} n={len(loss_cqis)}\n")
    if win_cqis and loss_cqis:
        sep = sum(win_cqis)/len(win_cqis) - sum(loss_cqis)/len(loss_cqis)
        out.write(f"  Separation (win_mean - loss_mean): {sep:+.3f}\n")

    # CQI CORRELATION WITH JUDGE DIMENSIONS
    out.write(f"\n--- CQI CORRELATION WITH JUDGE DIMENSIONS ---\n")
    out.write(f"{'Judge Dim':<25} {'Pearson':>8} {'Spearman':>9} {'95%CI_lo':>9} {'95%CI_hi':>9} {'CI∌0?':>6}\n")
    out.write("-" * W + "\n")
    for dim in JUDGE_DIMS:
        d_vals = [r.get(f"delta_{dim}", 0) for r in rows]
        p = pearson(cqi_vals, d_vals)
        s = spearman(cqi_vals, d_vals)
        bci = bootstrap_ci(cqi_vals, d_vals, n_boot=1000, seed=BOOTSTRAP_SEED)
        excl = "YES" if (bci["lo"] > 0 or bci["hi"] < 0) else "no"
        out.write(f"  {dim:<23} {p:>+8.3f} {s:>+9.3f} [{bci['lo']:>+8.3f}, {bci['hi']:>+8.3f}] {excl:>6}\n")

    # CQI vs WIN RATE: correlation with binary outcome
    wins_binary = [1.0 if r["win"] else 0.0 for r in rows]
    p_win = pearson(cqi_vals, wins_binary)
    s_win = spearman(cqi_vals, wins_binary)
    bci_win = bootstrap_ci(cqi_vals, wins_binary, n_boot=1000, seed=BOOTSTRAP_SEED)
    out.write(f"\n  CQI × win_binary       {p_win:>+8.3f} {s_win:>+9.3f} [{bci_win['lo']:>+8.3f}, {bci_win['hi']:>+8.3f}]\n")

    # PRECISION/RECALL AT THRESHOLDS
    out.write(f"\n--- PRECISION/RECALL FOR REGRESSION PREDICTION ---\n")
    out.write(f"  Predict: CQI >= threshold → expect improvement\n")
    out.write(f"           CQI <  threshold → expect regression\n\n")
    out.write(f"{'Thresh':>7} {'Acc':>5} {'P(good)':>8} {'R(good)':>8} {'F1(good)':>9} {'P(reg)':>7} {'R(reg)':>7} {'F1(reg)':>8} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}\n")
    out.write("-" * W + "\n")

    thresholds = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    best_f1 = 0.0
    best_thresh = 0.0
    wins_list = [r["win"] for r in rows]
    
    for thresh in thresholds:
        pr = precision_recall_at_threshold(cqi_vals, wins_list, thresh)
        avg_f1 = (pr["f1_good"] + pr["f1_reg"]) / 2
        if avg_f1 > best_f1:
            best_f1 = avg_f1
            best_thresh = thresh
        out.write(
            f"{thresh:>7.2f} {pr['accuracy']:>5.2f} {pr['precision_good']:>8.2f} {pr['recall_good']:>8.2f} "
            f"{pr['f1_good']:>9.2f} {pr['precision_reg']:>7.2f} {pr['recall_reg']:>7.2f} {pr['f1_reg']:>8.2f} "
            f"{pr['tp']:>3} {pr['fp']:>3} {pr['fn']:>3} {pr['tn']:>3}\n"
        )

    out.write(f"\n  Best threshold (avg F1): {best_thresh:.2f} → F1_avg={best_f1:.3f}\n")

    # HIGH vs LOW CQI BUCKETS
    out.write(f"\n--- HIGH vs LOW CQI ANALYSIS ---\n")
    
    # Top quartile vs bottom quartile
    q1 = n // 4
    top_quarter = rows[:q1] if q1 > 0 else rows[:1]
    bottom_quarter = rows[-q1:] if q1 > 0 else rows[-1:]
    
    top_wins = sum(1 for r in top_quarter if r["win"])
    top_total = len(top_quarter)
    bottom_wins = sum(1 for r in bottom_quarter if r["win"])
    bottom_total = len(bottom_quarter)
    
    out.write(f"  Top quartile  (CQI ≥ {top_quarter[-1]['cqi']:.3f}): {top_wins}/{top_total} wins ({100*top_wins/top_total:.0f}%)\n")
    out.write(f"  Bot quartile  (CQI ≤ {bottom_quarter[0]['cqi']:.3f}): {bottom_wins}/{bottom_total} wins ({100*bottom_wins/bottom_total:.0f}%)\n")
    
    # Top half vs bottom half
    mid = n // 2
    top_half = rows[:mid]
    bottom_half = rows[mid:]
    top_h_wins = sum(1 for r in top_half if r["win"])
    bot_h_wins = sum(1 for r in bottom_half if r["win"])
    
    out.write(f"  Top half      (CQI ≥ {top_half[-1]['cqi']:.3f}): {top_h_wins}/{len(top_half)} wins ({100*top_h_wins/len(top_half):.0f}%)\n")
    out.write(f"  Bot half      (CQI ≤ {bottom_half[0]['cqi']:.3f}): {bot_h_wins}/{len(bottom_half)} wins ({100*bot_h_wins/len(bottom_half):.0f}%)\n")
    
    # Mean ΔOQ per bucket
    top_h_delta = sum(r["overall_delta"] for r in top_half) / len(top_half)
    bot_h_delta = sum(r["overall_delta"] for r in bottom_half) / len(bottom_half)
    out.write(f"\n  Top half mean ΔOQ: {top_h_delta:+.1f}\n")
    out.write(f"  Bot half mean ΔOQ: {bot_h_delta:+.1f}\n")
    out.write(f"  Separation:        {top_h_delta - bot_h_delta:+.1f}\n")

    # FALSE POSITIVE / FALSE NEGATIVE ANALYSIS
    out.write(f"\n--- FALSE ANALYSIS (at best threshold {best_thresh:.2f}) ---\n")
    pr_best = precision_recall_at_threshold(cqi_vals, wins_list, best_thresh)
    
    # Show false positives (high CQI but lost)
    fp_queries = [r for r in rows if r["cqi"] >= best_thresh and not r["win"]]
    fn_queries = [r for r in rows if r["cqi"] < best_thresh and r["win"]]
    
    if fp_queries:
        out.write(f"\n  False Positives (CQI≥{best_thresh:.2f} but LOST, n={len(fp_queries)}):\n")
        for r in fp_queries:
            out.write(f"    CQI={r['cqi']:.3f} ΔOQ={r['overall_delta']:+.0f} | {r['query_text']}\n")
    
    if fn_queries:
        out.write(f"\n  False Negatives (CQI<{best_thresh:.2f} but WON, n={len(fn_queries)}):\n")
        for r in fn_queries:
            out.write(f"    CQI={r['cqi']:.3f} ΔOQ={r['overall_delta']:+.0f} | {r['query_text']}\n")

    # SUMMARY
    out.write(f"\n{'=' * W}\n")
    out.write("CQI SUMMARY\n")
    out.write(f"{'=' * W}\n\n")
    out.write(f"  CQI × overall_quality:  Pearson={p_win:+.3f}\n")
    ov_p = pearson(cqi_vals, [r.get("delta_overall_quality", 0) for r in rows])
    out.write(f"  CQI × ΔOQ (continuous): Pearson={ov_p:+.3f}\n")
    out.write(f"  Win-loss separation:    {sep:+.3f} (win_mean - loss_mean)\n")
    out.write(f"  Best threshold:         {best_thresh:.2f} (avg F1={best_f1:.3f})\n")
    out.write(f"  Top-half win rate:      {100*top_h_wins/len(top_half):.0f}%\n")
    out.write(f"  Bot-half win rate:      {100*bot_h_wins/len(bottom_half):.0f}%\n")
    out.write(f"{'=' * W}\n")


if __name__ == "__main__":
    main()
