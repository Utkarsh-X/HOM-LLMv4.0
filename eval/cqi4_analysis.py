"""
CQI_4 — Stable Dual-Axis Context Quality Index.

Mathematical formulation:
  Coherence Index:    CI  = α·z(M4) − β·z(M3)
  Ranking Confidence: RCI = γ·z(M5) + δ·z(M6)
  CQI_4 = sigmoid(0.5·CI + 0.5·RCI)

Weights: w_i = |r_i| / (1 + λ·drift_i), normalized per axis.
Z-scores: clipped to ±3, ε=1e-6 stability constant.

Includes:
  - CQI_5 vs CQI_4 comparison
  - 5-fold CV with both formulations
  - Judge swap comparison
  - Shadow threshold simulation
  - False positive gap analysis

Usage:
    set PYTHONIOENCODING=utf-8
    python eval/cqi4_analysis.py --conditions GPT_OSS=run_20260220_131016:judge_results__gpt-oss-120b.jsonl GEMINI=run_20260220_131016:judge_results__gemini-2.5-flash.jsonl
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
# CONSTANTS — from BASE20 correlation + CV analysis
# ──────────────────────────────────────────────────────────────────────────

# Correlation magnitudes with overall_quality (from 7-metric run)
R_VALUES = {
    "M4_content_overlap":    0.502,  # factual_consistency (strongest)
    "M5_score_separation":   0.520,  # overall_quality (strongest)
    "M3_file_entropy":       0.403,  # semantic_correctness (sign negative)
    "M6_reranker_influence":  0.389,  # overall_quality
    "M1_semantic_strength":   0.369,  # semantic_correctness
}

# Cross-validation weight drift (from 5-fold CV)
CV_DRIFT = {
    "M4_content_overlap":    0.008,   # 0.8%
    "M5_score_separation":   0.222,   # 22.2%
    "M3_file_entropy":       0.065,   # 6.5%
    "M6_reranker_influence":  0.176,   # 17.6%
    "M1_semantic_strength":   0.592,   # 59.2%
}

LAMBDA = 1.0  # drift penalty coefficient
EPSILON = 1e-6  # z-score stability constant
Z_CLIP = 3.0  # z-score clipping bound


# ──────────────────────────────────────────────────────────────────────────
# CQI_5 — Original 5-metric formulation (for comparison)
# ──────────────────────────────────────────────────────────────────────────

CQI5_RAW = {
    "M4_content_overlap":    0.502,
    "M5_score_separation":   0.520,
    "M3_file_entropy":      -0.403,
    "M6_reranker_influence":  0.389,
    "M1_semantic_strength":   0.369,
}
_abs5 = sum(abs(v) for v in CQI5_RAW.values())
CQI5_WEIGHTS = {k: v / _abs5 for k, v in CQI5_RAW.items()}
CQI5_METRICS = list(CQI5_WEIGHTS.keys())


# ──────────────────────────────────────────────────────────────────────────
# CQI_4 — Drift-penalized dual-axis formulation
# ──────────────────────────────────────────────────────────────────────────

CQI4_METRICS = ["M4_content_overlap", "M5_score_separation", "M3_file_entropy", "M6_reranker_influence"]

# Drift-penalized raw weights: w_i = |r_i| / (1 + λ·drift_i)
def _drift_weight(metric: str) -> float:
    return R_VALUES[metric] / (1.0 + LAMBDA * CV_DRIFT[metric])

# Coherence axis: M4(+) and M3(−)
_w4_raw = _drift_weight("M4_content_overlap")
_w3_raw = _drift_weight("M3_file_entropy")
_coh_total = _w4_raw + _w3_raw
ALPHA = _w4_raw / _coh_total  # M4 weight in coherence axis
BETA  = _w3_raw / _coh_total  # M3 weight in coherence axis (applied negative)

# Ranking confidence axis: M5(+) and M6(+)
_w5_raw = _drift_weight("M5_score_separation")
_w6_raw = _drift_weight("M6_reranker_influence")
_rci_total = _w5_raw + _w6_raw
GAMMA = _w5_raw / _rci_total  # M5 weight in ranking axis
DELTA = _w6_raw / _rci_total  # M6 weight in ranking axis


# ──────────────────────────────────────────────────────────────────────────
# Z-SCORE + CQI COMPUTATION
# ──────────────────────────────────────────────────────────────────────────

def compute_stats(rows: list[dict], metrics: list[str]) -> tuple[dict, dict]:
    """Compute means and stds for given metrics."""
    n = len(rows)
    means, stds = {}, {}
    for m in metrics:
        vals = [r.get(m, 0.0) or 0.0 for r in rows]
        mu = sum(vals) / n
        means[m] = mu
        stds[m] = math.sqrt(sum((v - mu) ** 2 for v in vals) / n)
    return means, stds


def z_score(val: float, mean: float, std: float) -> float:
    """Z-score with epsilon stability and ±3 clipping."""
    z = (val - mean) / (std + EPSILON)
    return max(-Z_CLIP, min(Z_CLIP, z))


def compute_cqi5(row: dict, means: dict, stds: dict) -> float:
    """CQI_5: original 5-metric flat weighted sigmoid."""
    z_sum = 0.0
    for m, w in CQI5_WEIGHTS.items():
        z_sum += w * z_score(row.get(m, 0.0) or 0.0, means.get(m, 0.0), stds.get(m, 1.0))
    return 1.0 / (1.0 + math.exp(-z_sum))


def compute_cqi4(row: dict, means: dict, stds: dict) -> tuple[float, float, float]:
    """CQI_4: dual-axis formulation.
    
    Returns: (cqi4, coherence_index, ranking_confidence_index)
    """
    z4 = z_score(row.get("M4_content_overlap", 0.0) or 0.0, means["M4_content_overlap"], stds["M4_content_overlap"])
    z3 = z_score(row.get("M3_file_entropy", 0.0) or 0.0, means["M3_file_entropy"], stds["M3_file_entropy"])
    z5 = z_score(row.get("M5_score_separation", 0.0) or 0.0, means["M5_score_separation"], stds["M5_score_separation"])
    z6 = z_score(row.get("M6_reranker_influence", 0.0) or 0.0, means["M6_reranker_influence"], stds["M6_reranker_influence"])
    
    ci  = ALPHA * z4 - BETA * z3   # Coherence: high overlap, low dispersion → good
    rci = GAMMA * z5 + DELTA * z6  # Ranking: sharp scores, strong reranker → good
    
    cqi4 = 1.0 / (1.0 + math.exp(-(0.5 * ci + 0.5 * rci)))
    return cqi4, ci, rci


# ──────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────────────────────────────────

def load_condition(run_name: str, judge_file: str | None = None) -> list[dict]:
    run_dir = RUNS_DIR / run_name
    if not run_dir.exists():
        print(f"ERROR: {run_dir}", file=sys.stderr)
        return []
    judge_path = run_dir / judge_file if judge_file else find_judge_file(run_dir)
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
# ANALYSIS HELPERS
# ──────────────────────────────────────────────────────────────────────────

def analyze_cqi(rows: list[dict], cqi_vals: list[float], label: str) -> dict:
    """Full analysis for a CQI variant."""
    n = len(rows)
    oq_vals = [r.get("delta_overall_quality", 0) for r in rows]
    win_vals = [1.0 if r["win"] else 0.0 for r in rows]

    p_oq = pearson(cqi_vals, oq_vals)
    s_oq = spearman(cqi_vals, oq_vals)
    bci_oq = bootstrap_ci(cqi_vals, oq_vals, n_boot=1000, seed=BOOTSTRAP_SEED)
    loo = loo_stability(cqi_vals, oq_vals)
    p_win = pearson(cqi_vals, win_vals)

    paired = sorted(zip(cqi_vals, [r["win"] for r in rows]), reverse=True)
    mid = n // 2
    top_wins = sum(1 for _, w in paired[:mid] if w)
    bot_wins = sum(1 for _, w in paired[mid:] if w)
    fps = sum(1 for c, r in zip(cqi_vals, rows) if c >= 0.50 and not r["win"])
    fns = sum(1 for c, r in zip(cqi_vals, rows) if c < 0.50 and r["win"])

    return {
        "label": label, "n": n, "wins": sum(r["win"] for r in rows),
        "p_oq": p_oq, "s_oq": s_oq,
        "ci_lo": bci_oq["lo"], "ci_hi": bci_oq["hi"],
        "ci_excl": bci_oq["lo"] > 0 or bci_oq["hi"] < 0,
        "loo_std": loo["std"], "p_win": p_win,
        "top_wins": top_wins, "top_n": mid,
        "bot_wins": bot_wins, "bot_n": n - mid,
        "fps": fps, "fns": fns,
    }


def run_cv(rows: list[dict], cqi_fn, metric_list: list[str], n_folds: int = 5, seed: int = 42):
    """K-fold CV for any CQI function."""
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

    fold_rs = []
    for fold_idx in range(n_folds):
        val_idx = set(folds[fold_idx])
        train = [rows[i] for i in range(n) if i not in val_idx]
        val = [rows[i] for i in folds[fold_idx]]
        means, stds = compute_stats(train, metric_list)
        val_cqis = [cqi_fn(r, means, stds) for r in val]
        # cqi_fn may return tuple (cqi4) or scalar (cqi5)
        if isinstance(val_cqis[0], tuple):
            val_cqis = [c[0] for c in val_cqis]
        val_deltas = [r.get("delta_overall_quality", 0) for r in val]
        r_val = pearson(val_cqis, val_deltas) if len(val_cqis) >= 3 else float('nan')
        fold_rs.append(r_val)

    valid = [r for r in fold_rs if not math.isnan(r)]
    mean_r = sum(valid) / len(valid) if valid else float('nan')
    std_r = math.sqrt(sum((v - mean_r)**2 for v in valid) / len(valid)) if len(valid) > 1 else 0
    return fold_rs, mean_r, std_r


# ──────────────────────────────────────────────────────────────────────────
# SHADOW THRESHOLD SIMULATION
# ──────────────────────────────────────────────────────────────────────────

def shadow_simulation(rows: list[dict], cqi_vals: list[float], out):
    """Simulate what would happen with CQI-based interventions."""
    out.write("\n  Shadow thresholds: what IF we had gated?\n\n")
    out.write(f"  {'Threshold':<12} {'Action':<25} {'Triggered':>9} {'Wins_lost':>10} {'Regs_caught':>12} {'NetΔWR':>7}\n")
    out.write("  " + "-" * 80 + "\n")

    total_wins = sum(1 for r in rows if r["win"])
    total_regs = sum(1 for r in rows if not r["win"])

    for thresh, action in [(0.40, "re-rank"), (0.35, "expand retrieval"), (0.30, "block generation")]:
        triggered = [(c, r) for c, r in zip(cqi_vals, rows) if c < thresh]
        n_triggered = len(triggered)
        wins_caught = sum(1 for _, r in triggered if r["win"])
        regs_caught = sum(1 for _, r in triggered if not r["win"])

        if action == "block generation":
            # Blocking saves generation cost but loses both wins and regressions
            net_wr_change = 0  # complex to model
            gen_saved = n_triggered
        else:
            gen_saved = 0
            net_wr_change = 0

        out.write(f"  CQI < {thresh:<5.2f} {action:<25} {n_triggered:>9} {wins_caught:>10} {regs_caught:>12}\n")

    out.write(f"\n  Base: {total_wins} wins, {total_regs} regressions out of {len(rows)}\n")


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CQI_4 dual-axis analysis")
    parser.add_argument("--conditions", nargs="+", required=True,
        help="LABEL=run_name[:judge_file]")
    args = parser.parse_args()

    out = sys.stdout
    W = 100

    # Parse + load
    conditions = {}
    for cond in args.conditions:
        parts = cond.split("=", 1)
        label = parts[0]
        rest = parts[1]
        run_name, judge_file = (rest.split(":", 1) + [None])[:2]
        conditions[label] = (run_name, judge_file)

    condition_data = {}
    for label, (run_name, judge_file) in conditions.items():
        rows = load_condition(run_name, judge_file)
        if rows:
            condition_data[label] = rows
            out.write(f"Loaded {label}: {len(rows)} queries\n")

    out.write("\n" + "=" * W + "\n")
    out.write("CQI_4 DUAL-AXIS FORMULATION — STABILITY ANALYSIS\n")
    out.write("=" * W + "\n")

    # ── ARCHITECTURE ──
    out.write(f"\n{'─' * W}\n")
    out.write("ARCHITECTURE\n")
    out.write(f"{'─' * W}\n\n")

    out.write("  CQI_4 = sigmoid(0.5·CI + 0.5·RCI)\n\n")
    out.write("  Coherence Index:     CI  = α·z(M4) − β·z(M3)\n")
    out.write("  Ranking Confidence:  RCI = γ·z(M5) + δ·z(M6)\n\n")

    out.write(f"  Drift-penalized weights: w_i = |r_i| / (1 + λ·drift_i), λ={LAMBDA}\n\n")
    out.write(f"  {'Metric':<25} {'|r|':>6} {'drift':>7} {'raw_w':>7} {'axis':>12} {'norm_w':>7}\n")
    out.write("  " + "-" * 70 + "\n")
    out.write(f"  {'M4_content_overlap':<25} {R_VALUES['M4_content_overlap']:>6.3f} {CV_DRIFT['M4_content_overlap']:>6.1%} {_w4_raw:>7.4f} {'Coherence':>12} α={ALPHA:>.4f}\n")
    out.write(f"  {'M3_file_entropy':<25} {R_VALUES['M3_file_entropy']:>6.3f} {CV_DRIFT['M3_file_entropy']:>6.1%} {_w3_raw:>7.4f} {'Coherence(−)':>12} β={BETA:>.4f}\n")
    out.write(f"  {'M5_score_separation':<25} {R_VALUES['M5_score_separation']:>6.3f} {CV_DRIFT['M5_score_separation']:>6.1%} {_w5_raw:>7.4f} {'Ranking':>12} γ={GAMMA:>.4f}\n")
    out.write(f"  {'M6_reranker_influence':<25} {R_VALUES['M6_reranker_influence']:>6.3f} {CV_DRIFT['M6_reranker_influence']:>6.1%} {_w6_raw:>7.4f} {'Ranking':>12} δ={DELTA:>.4f}\n")
    out.write(f"\n  Z-score: clipped to ±{Z_CLIP}, ε={EPSILON}\n")
    out.write(f"  M1 DROPPED (drift={CV_DRIFT['M1_semantic_strength']:.1%})\n")

    # ── COMPARISON: CQI_5 vs CQI_4 ──
    out.write(f"\n{'─' * W}\n")
    out.write("CQI_5 vs CQI_4 COMPARISON (per condition)\n")
    out.write(f"{'─' * W}\n\n")

    header = f"  {'Condition':<15} {'Ver':>5} {'r(OQ)':>7} {'ρ(OQ)':>7} {'CI_lo':>7} {'CI_hi':>7} {'CI∌0':>5} {'LOOσ':>6} {'r(w)':>6} {'TH%':>4} {'BH%':>4} {'FP':>3} {'FN':>3}\n"
    out.write(header)
    out.write("  " + "-" * 95 + "\n")

    all_results = {}
    for label, rows in condition_data.items():
        means5, stds5 = compute_stats(rows, CQI5_METRICS)
        means4, stds4 = compute_stats(rows, CQI4_METRICS)

        cqi5_vals = [compute_cqi5(r, means5, stds5) for r in rows]
        cqi4_results = [compute_cqi4(r, means4, stds4) for r in rows]
        cqi4_vals = [c[0] for c in cqi4_results]
        ci_vals = [c[1] for c in cqi4_results]
        rci_vals = [c[2] for c in cqi4_results]

        r5 = analyze_cqi(rows, cqi5_vals, f"{label}_5")
        r4 = analyze_cqi(rows, cqi4_vals, f"{label}_4")
        all_results[f"{label}_5"] = {**r5, "cqi_vals": cqi5_vals, "rows": rows}
        all_results[f"{label}_4"] = {**r4, "cqi_vals": cqi4_vals, "ci_vals": ci_vals, "rci_vals": rci_vals, "rows": rows}

        for ver, r in [("CQI_5", r5), ("CQI_4", r4)]:
            ci_f = "YES" if r["ci_excl"] else "no"
            th = f"{100*r['top_wins']/r['top_n']:.0f}" if r["top_n"] > 0 else "-"
            bh = f"{100*r['bot_wins']/r['bot_n']:.0f}" if r["bot_n"] > 0 else "-"
            out.write(
                f"  {label:<15} {ver:>5} {r['p_oq']:>+7.3f} {r['s_oq']:>+7.3f} "
                f"{r['ci_lo']:>+7.3f} {r['ci_hi']:>+7.3f} {ci_f:>5} {r['loo_std']:>6.3f} "
                f"{r['p_win']:>+6.3f} {th:>4} {bh:>4} {r['fps']:>3} {r['fns']:>3}\n"
            )
        out.write("\n")

    # ── 5-FOLD CV ──
    out.write(f"{'─' * W}\n")
    out.write("5-FOLD CROSS-VALIDATION\n")
    out.write(f"{'─' * W}\n\n")

    primary_rows = list(condition_data.values())[0]

    cv5_folds, cv5_mean, cv5_std = run_cv(primary_rows, compute_cqi5, CQI5_METRICS)
    cv4_folds, cv4_mean, cv4_std = run_cv(primary_rows, compute_cqi4, CQI4_METRICS)

    out.write(f"  {'Fold':>5} {'CQI_5':>8} {'CQI_4':>8}\n")
    out.write("  " + "-" * 25 + "\n")
    for i in range(len(cv5_folds)):
        v5 = f"{cv5_folds[i]:+.3f}" if not math.isnan(cv5_folds[i]) else "   N/A"
        v4 = f"{cv4_folds[i]:+.3f}" if not math.isnan(cv4_folds[i]) else "   N/A"
        out.write(f"  {i+1:>5} {v5:>8} {v4:>8}\n")

    out.write(f"\n  CQI_5 mean: {cv5_mean:+.3f} ± {cv5_std:.3f}\n")
    out.write(f"  CQI_4 mean: {cv4_mean:+.3f} ± {cv4_std:.3f}\n")

    improved = cv4_std < cv5_std
    out.write(f"\n  Fold variance: {'REDUCED' if improved else 'INCREASED'} ({cv5_std:.3f} → {cv4_std:.3f})\n")

    # ── PER-QUERY TABLE with axes ──
    out.write(f"\n{'─' * W}\n")
    out.write("PER-QUERY CQI_4 WITH AXIS DECOMPOSITION\n")
    out.write(f"{'─' * W}\n\n")

    primary_label = list(condition_data.keys())[0]
    r4_key = f"{primary_label}_4"
    r4_data = all_results[r4_key]

    out.write(f"  {'Rank':>4} {'CQI4':>6} {'CI':>6} {'RCI':>6} {'Win':>4} {'ΔOQ':>5} {'Zone':<10} {'Query':<45}\n")
    out.write("  " + "-" * 90 + "\n")

    # Sort by CQI_4
    sorted_idx = sorted(range(len(r4_data["rows"])), key=lambda i: -r4_data["cqi_vals"][i])
    for rank, i in enumerate(sorted_idx):
        row = r4_data["rows"][i]
        cqi = r4_data["cqi_vals"][i]
        ci = r4_data["ci_vals"][i]
        rci = r4_data["rci_vals"][i]

        if cqi >= 0.65:
            zone = "HIGH"
        elif cqi >= 0.50:
            zone = "GOOD"
        elif cqi >= 0.35:
            zone = "AMBIG"
        else:
            zone = "WEAK"

        win_s = " ✓" if row["win"] else " ✗"
        out.write(f"  {rank+1:>4} {cqi:>6.3f} {ci:>+6.2f} {rci:>+6.2f} {win_s:>4} {row['overall_delta']:>+5.0f} {zone:<10} {row['query_text']:<45}\n")

    # ── SHADOW SIMULATION ──
    out.write(f"\n{'─' * W}\n")
    out.write("SHADOW THRESHOLD SIMULATION (CQI_4)\n")
    out.write(f"{'─' * W}\n")

    for label, rows in condition_data.items():
        means4, stds4 = compute_stats(rows, CQI4_METRICS)
        cqi4_vals = [compute_cqi4(r, means4, stds4)[0] for r in rows]
        out.write(f"\n  [{label}]\n")
        shadow_simulation(rows, cqi4_vals, out)

    # ── FALSE POSITIVE GAP ANALYSIS ──
    out.write(f"\n{'─' * W}\n")
    out.write("FALSE POSITIVE GENERATION GAP ANALYSIS (CQI_4 ≥ 0.50 but lost)\n")
    out.write(f"{'─' * W}\n\n")

    fp_all = []
    for label, rows in condition_data.items():
        means4, stds4 = compute_stats(rows, CQI4_METRICS)
        for r in rows:
            cqi4, ci, rci = compute_cqi4(r, means4, stds4)
            if cqi4 >= 0.50 and not r["win"]:
                delta_fc = r.get("delta_factual_consistency", 0)
                delta_hr = r.get("delta_hallucination_risk", 0)
                delta_sc = r.get("delta_semantic_correctness", 0)
                delta_co = r.get("delta_completeness", 0)

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
                    "cond": label, "qid": r["query_id"], "query": r["query_text"],
                    "cqi4": cqi4, "ci": ci, "rci": rci,
                    "delta_oq": r["overall_delta"], "type": fp_type,
                    "delta_fc": delta_fc, "delta_hr": delta_hr,
                    "delta_sc": delta_sc, "delta_co": delta_co,
                })

    if fp_all:
        types = Counter(fp["type"] for fp in fp_all)
        out.write(f"  Total FPs: {len(fp_all)}\n")
        for t, c in types.most_common():
            out.write(f"    {t}: {c} ({100*c/len(fp_all):.0f}%)\n")

        out.write(f"\n  {'Cond':<10} {'CQI4':>5} {'CI':>5} {'RCI':>5} {'ΔOQ':>4} {'ΔFC':>4} {'ΔHR':>4} {'Type':<18} {'Query':<40}\n")
        out.write("  " + "-" * 95 + "\n")
        for fp in sorted(fp_all, key=lambda x: -x["cqi4"]):
            out.write(
                f"  {fp['cond']:<10} {fp['cqi4']:>5.3f} {fp['ci']:>+5.2f} {fp['rci']:>+5.2f} "
                f"{fp['delta_oq']:>+4.0f} {fp['delta_fc']:>+4.0f} {fp['delta_hr']:>+4.0f} "
                f"{fp['type']:<18} {fp['query']:<40}\n"
            )

        # Axis analysis for FPs
        fp_ci_mean = sum(fp["ci"] for fp in fp_all) / len(fp_all)
        fp_rci_mean = sum(fp["rci"] for fp in fp_all) / len(fp_all)
        out.write(f"\n  FP axis means: CI={fp_ci_mean:+.2f} RCI={fp_rci_mean:+.2f}\n")
        if abs(fp_ci_mean) > abs(fp_rci_mean):
            out.write(f"  → FPs tend to have {'high coherence' if fp_ci_mean > 0 else 'low coherence'} — generation issue, not context issue\n")
        else:
            out.write(f"  → FPs tend to have {'high ranking confidence' if fp_rci_mean > 0 else 'low ranking confidence'}\n")
    else:
        out.write("  No false positives.\n")

    # ── VERDICT ──
    out.write(f"\n{'=' * W}\n")
    out.write("CQI_4 vs CQI_5 STABILITY VERDICT\n")
    out.write(f"{'=' * W}\n\n")

    out.write(f"  {'Criterion':<35} {'CQI_5':>10} {'CQI_4':>10} {'Winner':>10}\n")
    out.write("  " + "-" * 70 + "\n")

    # Gather primary condition stats
    p5 = all_results.get(f"{primary_label}_5", {})
    p4 = all_results.get(f"{primary_label}_4", {})

    criteria = [
        ("r(OQ) primary", f"{p5.get('p_oq',0):+.3f}", f"{p4.get('p_oq',0):+.3f}",
         "CQI_4" if abs(p4.get("p_oq", 0)) >= abs(p5.get("p_oq", 0)) else "CQI_5"),
        ("CV fold variance", f"{cv5_std:.3f}", f"{cv4_std:.3f}",
         "CQI_4" if cv4_std <= cv5_std else "CQI_5"),
        ("CV mean r(OQ)", f"{cv5_mean:+.3f}", f"{cv4_mean:+.3f}",
         "CQI_4" if cv4_mean >= cv5_mean else "CQI_5"),
        ("LOO σ primary", f"{p5.get('loo_std',0):.3f}", f"{p4.get('loo_std',0):.3f}",
         "CQI_4" if p4.get("loo_std", 1) <= p5.get("loo_std", 1) else "CQI_5"),
        ("Bot-half win% primary", f"{100*p5.get('bot_wins',0)/max(p5.get('bot_n',1),1):.0f}%",
         f"{100*p4.get('bot_wins',0)/max(p4.get('bot_n',1),1):.0f}%",
         "TIE" if p4.get('bot_wins',0) == p5.get('bot_wins',0) else
         "CQI_4" if p4.get('bot_wins',0) < p5.get('bot_wins',0) else "CQI_5"),
    ]

    cqi4_wins = 0
    for name, v5, v4, winner in criteria:
        out.write(f"  {name:<35} {v5:>10} {v4:>10} {winner:>10}\n")
        if winner == "CQI_4":
            cqi4_wins += 1

    out.write(f"\n  CQI_4 wins: {cqi4_wins}/{len(criteria)}\n")
    if cqi4_wins >= 3:
        out.write("  → CQI_4 is SUPERIOR: more stable, recommended for production.\n")
    elif cqi4_wins >= 2:
        out.write("  → CQI_4 is COMPARABLE: stability gain offsets slight r(OQ) change.\n")
    else:
        out.write("  → CQI_5 remains better: dropping M1 did not improve stability.\n")

    out.write(f"{'=' * W}\n")


if __name__ == "__main__":
    main()
