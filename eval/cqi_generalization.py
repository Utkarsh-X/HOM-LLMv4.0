"""
CQI Generalization Validation — Cross-Validation + Multi-Condition Analysis.

Phase 1: 5-fold cross-validation (weight generalization)
Phase 2: Multi-condition comparison (judge swap, perturbation runs)
Phase 3: Weight drift + false positive classification
Phase 4: Final verdict

Usage:
    set PYTHONIOENCODING=utf-8
    python eval/cqi_generalization.py --conditions BASE20=run_20260220_131016 [JUDGE2=run_X:judge_file] [PERTURB_LO=run_Y] ...
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path

from signal_correlation_base20 import (
    compute_all_metrics,
    JUDGE_DIMS,
    RUNS_DIR,
    find_judge_file,
    load_responses,
    load_judge,
    pearson,
    spearman,
    bootstrap_ci,
    loo_stability,
    BOOTSTRAP_SEED,
)

# ──────────────────────────────────────────────────────────────────────────
# CQI (same formula as cqi_analysis.py)
# ──────────────────────────────────────────────────────────────────────────

CQI_METRICS = [
    "M4_content_overlap",
    "M5_score_separation",
    "M3_file_entropy",
    "M6_reranker_influence",
    "M1_semantic_strength",
]

BASELINE_WEIGHTS = {
    "M4_content_overlap":    0.502,
    "M5_score_separation":   0.520,
    "M3_file_entropy":      -0.403,
    "M6_reranker_influence":  0.389,
    "M1_semantic_strength":   0.369,
}
_abs_sum = sum(abs(v) for v in BASELINE_WEIGHTS.values())
BASELINE_WEIGHTS_NORM = {k: v / _abs_sum for k, v in BASELINE_WEIGHTS.items()}


def derive_weights(rows: list[dict], target_dim: str = "delta_overall_quality") -> dict[str, float]:
    """Derive CQI weights from correlation magnitudes for a subset of rows."""
    raw = {}
    for m in CQI_METRICS:
        m_vals = [r[m] for r in rows]
        d_vals = [r.get(target_dim, 0) for r in rows]
        r_val = pearson(m_vals, d_vals)
        raw[m] = r_val
    total = sum(abs(v) for v in raw.values())
    if total < 1e-10:
        return {m: 0.0 for m in CQI_METRICS}
    return {m: v / total for m, v in raw.items()}


def compute_cqi(metrics: dict, means: dict, stds: dict, weights: dict) -> float:
    """CQI = sigmoid(Σ w_i × z_i)."""
    z_sum = 0.0
    for m, w in weights.items():
        val = metrics.get(m, 0.0) or 0.0
        std = stds.get(m, 1.0)
        if std < 1e-10:
            std = 1.0
        z = (val - means.get(m, 0.0)) / std
        z_sum += w * z
    return 1.0 / (1.0 + math.exp(-z_sum))


def compute_means_stds(rows: list[dict]) -> tuple[dict, dict]:
    n = len(rows)
    means, stds = {}, {}
    for m in CQI_METRICS:
        vals = [r[m] for r in rows]
        mu = sum(vals) / n
        means[m] = mu
        stds[m] = math.sqrt(sum((v - mu) ** 2 for v in vals) / n)
    return means, stds


# ──────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────────────────────────────────

def load_condition(run_name: str, judge_file: str | None = None) -> list[dict]:
    """Load a full condition: responses + telemetry + judge → rows."""
    run_dir = RUNS_DIR / run_name
    if not run_dir.exists():
        print(f"ERROR: {run_dir}", file=sys.stderr)
        return []
    if judge_file:
        judge_path = run_dir / judge_file
    else:
        judge_path = find_judge_file(run_dir)
    responses = load_responses(run_dir)
    judge_results = load_judge(judge_path)

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
        overall_delta = deltas.get("overall_quality", 0)
        row = {
            "query_id": qid,
            "query_text": resp.get("query_text", "")[:60],
            "win": overall_delta > 0,
            "overall_delta": overall_delta,
            **{k: (v if v is not None else 0.0) for k, v in metrics.items()},
            **{f"delta_{d}": v for d, v in deltas.items()},
        }
        rows.append(row)
    return rows


# ──────────────────────────────────────────────────────────────────────────
# 5-FOLD CROSS-VALIDATION
# ──────────────────────────────────────────────────────────────────────────

def run_cross_validation(rows: list[dict], n_folds: int = 5, seed: int = 42) -> dict:
    """K-fold CV: train weights on k-1 folds, validate CQI on held-out fold."""
    n = len(rows)
    rng = random.Random(seed)
    indices = list(range(n))
    rng.shuffle(indices)

    fold_size = n // n_folds
    folds = []
    for i in range(n_folds):
        start = i * fold_size
        end = start + fold_size if i < n_folds - 1 else n
        folds.append(indices[start:end])

    fold_results = []
    all_weights = []

    for fold_idx in range(n_folds):
        val_indices = set(folds[fold_idx])
        train_rows = [rows[i] for i in range(n) if i not in val_indices]
        val_rows = [rows[i] for i in folds[fold_idx]]

        # Derive weights from training set
        fold_weights = derive_weights(train_rows)
        all_weights.append(fold_weights)

        # Compute CQI using training set stats
        train_means, train_stds = compute_means_stds(train_rows)

        # Apply to validation set
        val_cqis = []
        val_deltas = []
        val_wins = []
        for r in val_rows:
            cqi = compute_cqi(r, train_means, train_stds, fold_weights)
            val_cqis.append(cqi)
            val_deltas.append(r.get("delta_overall_quality", 0))
            val_wins.append(1.0 if r["win"] else 0.0)

        # Correlation on validation set (may be small n, so handle gracefully)
        p_oq = pearson(val_cqis, val_deltas) if len(val_cqis) >= 3 else float('nan')
        p_win = pearson(val_cqis, val_wins) if len(val_cqis) >= 3 else float('nan')

        fold_results.append({
            "fold": fold_idx + 1,
            "train_n": len(train_rows),
            "val_n": len(val_rows),
            "pearson_oq": p_oq,
            "pearson_win": p_win,
            "val_cqis": val_cqis,
            "val_deltas": val_deltas,
            "val_wins": val_wins,
            "weights": fold_weights,
        })

    return {"folds": fold_results, "all_weights": all_weights}


# ──────────────────────────────────────────────────────────────────────────
# CONDITION ANALYSIS
# ──────────────────────────────────────────────────────────────────────────

def analyze_condition(rows: list[dict], weights: dict, label: str) -> dict:
    """Full CQI analysis for one condition."""
    n = len(rows)
    means, stds = compute_means_stds(rows)

    cqi_vals = [compute_cqi(r, means, stds, weights) for r in rows]
    oq_vals = [r.get("delta_overall_quality", 0) for r in rows]
    win_vals = [1.0 if r["win"] else 0.0 for r in rows]

    # Correlations
    p_oq = pearson(cqi_vals, oq_vals)
    s_oq = spearman(cqi_vals, oq_vals)
    bci_oq = bootstrap_ci(cqi_vals, oq_vals, n_boot=1000, seed=BOOTSTRAP_SEED)
    loo_oq = loo_stability(cqi_vals, oq_vals)

    p_win = pearson(cqi_vals, win_vals)
    s_win = spearman(cqi_vals, win_vals)
    bci_win = bootstrap_ci(cqi_vals, win_vals, n_boot=1000, seed=BOOTSTRAP_SEED)

    # Win rate by half
    paired = sorted(zip(cqi_vals, [r["win"] for r in rows]), reverse=True)
    mid = n // 2
    top_wins = sum(1 for _, w in paired[:mid] if w)
    bot_wins = sum(1 for _, w in paired[mid:] if w)

    # Derive condition-specific weights
    cond_weights = derive_weights(rows)

    # False positives at 0.50
    fps = sum(1 for c, r in zip(cqi_vals, rows) if c >= 0.50 and not r["win"])
    fns = sum(1 for c, r in zip(cqi_vals, rows) if c < 0.50 and r["win"])

    return {
        "label": label,
        "n": n,
        "wins": sum(r["win"] for r in rows),
        "p_oq": p_oq, "s_oq": s_oq,
        "ci_lo": bci_oq["lo"], "ci_hi": bci_oq["hi"],
        "ci_excludes_zero": bci_oq["lo"] > 0 or bci_oq["hi"] < 0,
        "loo_mean": loo_oq["mean"], "loo_std": loo_oq["std"],
        "p_win": p_win, "s_win": s_win,
        "ci_win_lo": bci_win["lo"], "ci_win_hi": bci_win["hi"],
        "top_half_wins": top_wins, "top_half_n": mid,
        "bot_half_wins": bot_wins, "bot_half_n": n - mid,
        "fps_at_50": fps, "fns_at_50": fns,
        "cond_weights": cond_weights,
        "cqi_vals": cqi_vals,
        "rows": rows,
    }


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CQI generalization analysis")
    parser.add_argument(
        "--conditions", nargs="+", required=True,
        help="Conditions as LABEL=run_name[:judge_file], e.g. BASE20=run_20260220_131016"
    )
    args = parser.parse_args()

    out = sys.stdout
    W = 100

    # Parse conditions
    conditions = {}
    for cond in args.conditions:
        parts = cond.split("=", 1)
        label = parts[0]
        rest = parts[1] if len(parts) > 1 else parts[0]
        if ":" in rest:
            run_name, judge_file = rest.split(":", 1)
        else:
            run_name, judge_file = rest, None
        conditions[label] = (run_name, judge_file)

    # Load all conditions
    condition_data = {}
    for label, (run_name, judge_file) in conditions.items():
        rows = load_condition(run_name, judge_file)
        if rows:
            condition_data[label] = rows
            out.write(f"Loaded {label}: {len(rows)} queries from {run_name}\n")
        else:
            out.write(f"WARNING: Failed to load {label}\n")

    if not condition_data:
        out.write("ERROR: No conditions loaded\n")
        sys.exit(1)

    out.write("\n" + "=" * W + "\n")
    out.write("CQI GENERALIZATION VALIDATION REPORT\n")
    out.write("=" * W + "\n")

    # ──────────────────────────────────────────────────────────────────
    # PHASE 1: 5-FOLD CROSS-VALIDATION (on first condition)
    # ──────────────────────────────────────────────────────────────────

    primary_label = list(condition_data.keys())[0]
    primary_rows = condition_data[primary_label]

    out.write(f"\n{'─' * W}\n")
    out.write(f"PHASE 1: 5-FOLD CROSS-VALIDATION ({primary_label}, n={len(primary_rows)})\n")
    out.write(f"{'─' * W}\n\n")

    cv = run_cross_validation(primary_rows)

    out.write(f"{'Fold':>5} {'Train':>6} {'Val':>4} {'r(OQ)':>7} {'r(win)':>7}\n")
    out.write("-" * 40 + "\n")

    valid_oq = []
    valid_win = []
    for f in cv["folds"]:
        oq_str = f"{f['pearson_oq']:+.3f}" if not math.isnan(f["pearson_oq"]) else "  N/A"
        win_str = f"{f['pearson_win']:+.3f}" if not math.isnan(f["pearson_win"]) else "  N/A"
        out.write(f"  {f['fold']:>3} {f['train_n']:>6} {f['val_n']:>4} {oq_str:>7} {win_str:>7}\n")
        if not math.isnan(f["pearson_oq"]):
            valid_oq.append(f["pearson_oq"])
        if not math.isnan(f["pearson_win"]):
            valid_win.append(f["pearson_win"])

    if valid_oq:
        mean_oq = sum(valid_oq) / len(valid_oq)
        std_oq = math.sqrt(sum((v - mean_oq)**2 for v in valid_oq) / len(valid_oq)) if len(valid_oq) > 1 else 0
        out.write(f"\n  CV mean r(OQ):  {mean_oq:+.3f} ± {std_oq:.3f}\n")
    if valid_win:
        mean_win = sum(valid_win) / len(valid_win)
        out.write(f"  CV mean r(win): {mean_win:+.3f}\n")

    # Weight stability across folds
    out.write(f"\n  Weight stability across folds:\n")
    header = f"  {'Metric':<25} "
    for i in range(len(cv["all_weights"])):
        header += f"{'F'+str(i+1):>7} "
    header += f"{'Std':>7} {'Drift%':>7}\n"
    out.write(header)
    out.write("  " + "-" * (25 + 7 * (len(cv["all_weights"]) + 2)) + "\n")

    weight_drifts = []
    for m in CQI_METRICS:
        fold_vals = [w[m] for w in cv["all_weights"]]
        baseline_w = BASELINE_WEIGHTS_NORM[m]
        avg = sum(fold_vals) / len(fold_vals)
        std = math.sqrt(sum((v - avg)**2 for v in fold_vals) / len(fold_vals)) if len(fold_vals) > 1 else 0
        drift_pct = abs(avg - baseline_w) / abs(baseline_w) * 100 if abs(baseline_w) > 1e-10 else 0
        weight_drifts.append(drift_pct)

        out.write(f"  {m:<25} ")
        for v in fold_vals:
            out.write(f"{v:>+7.3f} ")
        out.write(f"{std:>7.3f} {drift_pct:>6.1f}%\n")

    avg_drift = sum(weight_drifts) / len(weight_drifts)
    out.write(f"\n  Mean weight drift from baseline: {avg_drift:.1f}%\n")
    cv_weight_stable = avg_drift < 15
    out.write(f"  Weight stability: {'STABLE' if cv_weight_stable else 'UNSTABLE'} (threshold: <15%)\n")

    # ──────────────────────────────────────────────────────────────────
    # PHASE 2: MULTI-CONDITION ANALYSIS
    # ──────────────────────────────────────────────────────────────────

    out.write(f"\n{'─' * W}\n")
    out.write(f"PHASE 2: CROSS-CONDITION COMPARISON\n")
    out.write(f"{'─' * W}\n\n")

    results = {}
    for label, rows in condition_data.items():
        result = analyze_condition(rows, BASELINE_WEIGHTS_NORM, label)
        results[label] = result

    # Cross-condition table
    out.write(f"{'Condition':<20} {'n':>3} {'W':>3} {'r(OQ)':>7} {'ρ(OQ)':>7} {'CI_lo':>7} {'CI_hi':>7} {'CI∌0':>5} {'LOOσ':>6} {'r(win)':>7} {'TH%':>4} {'BH%':>4} {'FP':>3} {'FN':>3}\n")
    out.write("-" * W + "\n")

    for label, r in results.items():
        ci_flag = "YES" if r["ci_excludes_zero"] else "no"
        th_pct = f"{100*r['top_half_wins']/r['top_half_n']:.0f}" if r["top_half_n"] > 0 else "-"
        bh_pct = f"{100*r['bot_half_wins']/r['bot_half_n']:.0f}" if r["bot_half_n"] > 0 else "-"
        out.write(
            f"{label:<20} {r['n']:>3} {r['wins']:>3} {r['p_oq']:>+7.3f} {r['s_oq']:>+7.3f} "
            f"{r['ci_lo']:>+7.3f} {r['ci_hi']:>+7.3f} {ci_flag:>5} {r['loo_std']:>6.3f} "
            f"{r['p_win']:>+7.3f} {th_pct:>4} {bh_pct:>4} {r['fps_at_50']:>3} {r['fns_at_50']:>3}\n"
        )

    # ──────────────────────────────────────────────────────────────────
    # PHASE 3: WEIGHT DRIFT ACROSS CONDITIONS
    # ──────────────────────────────────────────────────────────────────

    if len(results) > 1:
        out.write(f"\n{'─' * W}\n")
        out.write(f"PHASE 3: WEIGHT DRIFT ACROSS CONDITIONS\n")
        out.write(f"{'─' * W}\n\n")

        out.write(f"{'Metric':<25} {'Baseline':>8} ")
        for label in results:
            out.write(f"{label:>12} ")
        out.write(f"{'Std':>7} {'MaxDrift%':>10}\n")
        out.write("-" * W + "\n")

        cond_weight_drifts = []
        for m in CQI_METRICS:
            baseline_w = BASELINE_WEIGHTS_NORM[m]
            cond_vals = [results[label]["cond_weights"][m] for label in results]
            all_vals = [baseline_w] + cond_vals
            avg = sum(all_vals) / len(all_vals)
            std = math.sqrt(sum((v - avg)**2 for v in all_vals) / len(all_vals))
            max_drift = max(abs(v - baseline_w) / abs(baseline_w) * 100 for v in cond_vals) if abs(baseline_w) > 1e-10 else 0
            cond_weight_drifts.append(max_drift)

            out.write(f"{m:<25} {baseline_w:>+8.4f} ")
            for label in results:
                out.write(f"{results[label]['cond_weights'][m]:>+12.4f} ")
            out.write(f"{std:>7.4f} {max_drift:>9.1f}%\n")

        avg_cond_drift = sum(cond_weight_drifts) / len(cond_weight_drifts)
        out.write(f"\n  Mean max weight drift: {avg_cond_drift:.1f}%\n")

    # ──────────────────────────────────────────────────────────────────
    # PHASE 4: FALSE POSITIVE CLASSIFICATION
    # ──────────────────────────────────────────────────────────────────

    out.write(f"\n{'─' * W}\n")
    out.write(f"PHASE 4: FALSE POSITIVE ANALYSIS (CQI ≥ 0.50 but lost)\n")
    out.write(f"{'─' * W}\n\n")

    fp_all = []
    for label, r in results.items():
        cqis = r["cqi_vals"]
        for i, row in enumerate(r["rows"]):
            if cqis[i] >= 0.50 and not row["win"]:
                # Classify FP type
                delta_fc = row.get("delta_factual_consistency", 0)
                delta_hr = row.get("delta_hallucination_risk", 0)
                delta_sc = row.get("delta_semantic_correctness", 0)
                delta_co = row.get("delta_completeness", 0)
                
                if delta_hr <= -3:
                    fp_type = "HALLUCINATION"
                elif delta_fc <= -3:
                    fp_type = "FACTUAL_FAILURE"
                elif delta_sc <= -2:
                    fp_type = "SEMANTIC_MISS"
                elif delta_co <= -2:
                    fp_type = "INCOMPLETE"
                else:
                    fp_type = "BASELINE_STRONG"
                
                fp_all.append({
                    "condition": label,
                    "query": row["query_text"],
                    "cqi": cqis[i],
                    "delta_oq": row["overall_delta"],
                    "type": fp_type,
                    "delta_fc": delta_fc,
                    "delta_hr": delta_hr,
                    "delta_sc": delta_sc,
                })

    if fp_all:
        # Count by type
        type_counts = Counter(fp["type"] for fp in fp_all)
        out.write(f"  Total FPs: {len(fp_all)}\n")
        for t, c in type_counts.most_common():
            out.write(f"    {t}: {c} ({100*c/len(fp_all):.0f}%)\n")

        out.write(f"\n  {'Cond':<12} {'CQI':>5} {'ΔOQ':>4} {'Type':<18} {'Query':<50}\n")
        out.write("  " + "-" * 90 + "\n")
        for fp in sorted(fp_all, key=lambda x: -x["cqi"]):
            out.write(f"  {fp['condition']:<12} {fp['cqi']:>5.3f} {fp['delta_oq']:>+4.0f} {fp['type']:<18} {fp['query']:<50}\n")
    else:
        out.write("  No false positives found.\n")

    # ──────────────────────────────────────────────────────────────────
    # VERDICT
    # ──────────────────────────────────────────────────────────────────

    out.write(f"\n{'=' * W}\n")
    out.write("FINAL VERDICT\n")
    out.write(f"{'=' * W}\n\n")

    # Gather criteria
    criteria = {
        "r_oq_all_above_045": all(r["p_oq"] >= 0.45 for r in results.values()),
        "ci_all_exclude_zero": all(r["ci_excludes_zero"] for r in results.values()),
        "loo_all_below_010": all(r["loo_std"] < 0.10 for r in results.values()),
        "bot_half_low_winrate": all(
            r["bot_half_wins"] / r["bot_half_n"] <= 0.15 if r["bot_half_n"] > 0 else True
            for r in results.values()
        ),
    }

    # Weight drift (use CV if single condition, cross-condition if multiple)
    if len(results) > 1:
        criteria["weight_drift_below_15"] = avg_cond_drift < 15
    else:
        criteria["weight_drift_below_15"] = cv_weight_stable

    # CV performance
    if valid_oq:
        criteria["cv_mean_r_above_0"] = mean_oq > 0

    out.write("  Criteria:\n")
    for k, v in criteria.items():
        status = "✓ PASS" if v else "✗ FAIL"
        out.write(f"    {status}  {k}\n")

    passed = sum(criteria.values())
    total = len(criteria)

    out.write(f"\n  Score: {passed}/{total} criteria passed\n\n")

    if passed >= total - 1 and criteria.get("r_oq_all_above_045", False):
        out.write("  VERDICT: Case 1 — Robust Generalizable Signal\n")
        out.write("  CQI is stable across conditions and generalizes well.\n")
    elif passed >= total // 2:
        out.write("  VERDICT: Case 2 — Moderate but Stable\n")
        out.write("  CQI shows moderate generalization with some condition sensitivity.\n")
    else:
        out.write("  VERDICT: Case 3 — Dataset-Specific Artifact\n")
        out.write("  CQI may be overfit to the training dataset.\n")

    out.write(f"{'=' * W}\n")


if __name__ == "__main__":
    main()
