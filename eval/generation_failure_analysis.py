"""
Phase 5 — Generation Failure Analysis + GCI + Experimental Protocol.

Task 1: Classifies generation failures using answer_validator dimensions.
Task 3: Computes Generation Confidence Index (GCI).
Task 5: Runs experimental comparisons.

Usage:
    set PYTHONIOENCODING=utf-8
    python eval/generation_failure_analysis.py --run run_20260220_131016
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from collections import Counter

# Add src to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from homllm.quality.answer_validator import validate_answer, classify_query_type

from signal_correlation_base20 import (
    RUNS_DIR,
    JUDGE_DIMS,
    find_judge_file,
    load_responses,
    load_judge,
    pearson,
    spearman,
    bootstrap_ci,
    BOOTSTRAP_SEED,
)

# ── CQI_4 (from cqi4_analysis.py) ──
from cqi4_analysis import (
    compute_cqi4,
    compute_stats,
    CQI4_METRICS,
    compute_all_metrics,
)


# ──────────────────────────────────────────────────────────────────────────
# GCI — Generation Confidence Index
# ──────────────────────────────────────────────────────────────────────────

EPSILON = 1e-6
Z_CLIP = 3.0

def _z(val: float, mean: float, std: float) -> float:
    z = (val - mean) / (std + EPSILON)
    return max(-Z_CLIP, min(Z_CLIP, z))


def compute_gci(
    structure_score: float,
    evidence_density: float,
    answer_depth: float,
    contradiction_score: float,
    stats: dict,
) -> tuple[float, dict]:
    """GCI = sigmoid(a·z(structure) + b·z(evidence) + c·z(depth) − d·z(contradiction))
    
    Equal weights initially (a=b=c=d=0.25).
    Returns (gci, components_dict).
    """
    z_struct = _z(structure_score, stats["struct_mean"], stats["struct_std"])
    z_evid = _z(evidence_density, stats["evid_mean"], stats["evid_std"])
    z_depth = _z(answer_depth, stats["depth_mean"], stats["depth_std"])
    z_contra = _z(contradiction_score, stats["contra_mean"], stats["contra_std"])

    linear = 0.25 * z_struct + 0.25 * z_evid + 0.25 * z_depth - 0.25 * z_contra
    gci = 1.0 / (1.0 + math.exp(-linear))

    return gci, {
        "z_structure": round(z_struct, 3),
        "z_evidence": round(z_evid, 3),
        "z_depth": round(z_depth, 3),
        "z_contradiction": round(z_contra, 3),
    }


def compute_gci_stats(rows: list[dict]) -> dict:
    """Compute means/stds for GCI components."""
    def _stats(vals):
        mu = sum(vals) / len(vals) if vals else 0
        sigma = math.sqrt(sum((v - mu)**2 for v in vals) / len(vals)) if len(vals) > 1 else 1
        return mu, sigma

    struct_vals = [r["validation"]["structure_score"] for r in rows]
    evid_vals = [r["validation"]["dimensions"]["evidence_density"] for r in rows]
    depth_vals = [r["validation"]["dimensions"]["answer_depth"] for r in rows]
    contra_vals = [r["validation"]["dimensions"]["contradiction_score"] for r in rows]

    sm, ss = _stats(struct_vals)
    em, es = _stats(evid_vals)
    dm, ds = _stats(depth_vals)
    cm, cs = _stats(contra_vals)

    return {
        "struct_mean": sm, "struct_std": ss,
        "evid_mean": em, "evid_std": es,
        "depth_mean": dm, "depth_std": ds,
        "contra_mean": cm, "contra_std": cs,
    }


# ──────────────────────────────────────────────────────────────────────────
# FAILURE CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────────

def classify_failure(row: dict) -> str:
    """Classify generation failure type from judge scores + validator."""
    delta_oq = row.get("overall_delta", 0)
    if delta_oq >= 0:
        return "WIN"

    delta_fc = row.get("delta_factual_consistency", 0)
    delta_hr = row.get("delta_hallucination_risk", 0)
    delta_sc = row.get("delta_semantic_correctness", 0)
    delta_co = row.get("delta_completeness", 0)

    val = row.get("validation", {})
    struct = val.get("structure_score", 0.5)
    dims = val.get("dimensions", {})

    # Priority classification
    if delta_hr <= -3 or dims.get("contradiction_score", 0) > 0.5:
        return "HALLUCINATION"
    if delta_co <= -2 or struct < 0.4:
        return "INCOMPLETE"
    if delta_sc <= -2 or dims.get("entity_coverage", 1) < 0.3:
        return "SEMANTIC_MISS"
    return "BASELINE_STRONG"


# ──────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────────────────────────────────

def load_full_data(run_name: str, judge_file: str | None = None) -> list[dict]:
    """Load run data with validation scores."""
    run_dir = RUNS_DIR / run_name
    judge_path = run_dir / judge_file if judge_file else find_judge_file(run_dir)
    responses = load_responses(run_dir)
    judge_results = load_judge(judge_path)

    # Load baseline for comparison
    baseline_path = ROOT / "eval" / "cursor_baseline.json"
    baseline = {}
    if baseline_path.exists():
        bp = json.load(open(baseline_path, "r", encoding="utf-8"))
        for q in bp.get("queries", []):
            baseline[q["query_id"]] = q.get("answer", "")

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

        answer_text = resp.get("answer_text", "")
        query_text = resp.get("query_text", "")
        drop_trace = telemetry.get("CONTEXT", {}).get("drop_trace", [])
        ctx_tokens = telemetry.get("CONTEXT", {}).get("tokens", 0)

        # Run answer validator
        validation = validate_answer(query_text, answer_text, drop_trace, ctx_tokens)

        # Also validate baseline
        baseline_answer = baseline.get(qid, "")
        baseline_validation = validate_answer(query_text, baseline_answer, drop_trace, ctx_tokens)

        row = {
            "query_id": qid,
            "query_text": query_text[:60],
            "full_query": query_text,
            "win": deltas.get("overall_quality", 0) > 0,
            "overall_delta": deltas.get("overall_quality", 0),
            "answer_len": len(answer_text),
            "baseline_len": len(baseline_answer),
            "tokens_out": resp.get("tokens_out", 0),
            "validation": validation,
            "baseline_validation": baseline_validation,
            **{k: (v if v is not None else 0.0) for k, v in metrics.items()},
            **{f"delta_{d}": v for d, v in deltas.items()},
        }
        rows.append(row)

    return rows


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase 5: Generation failure analysis")
    parser.add_argument("--run", required=True, help="Run name")
    parser.add_argument("--judge", default=None, help="Judge file name")
    args = parser.parse_args()

    out = sys.stdout
    W = 100

    rows = load_full_data(args.run, args.judge)
    if not rows:
        out.write("ERROR: No data loaded\n")
        sys.exit(1)

    out.write(f"Loaded {len(rows)} queries from {args.run}\n")

    # ── TASK 1: FAILURE TAXONOMY ──
    out.write("\n" + "=" * W + "\n")
    out.write("PHASE 5 — GENERATION ROBUSTNESS ANALYSIS\n")
    out.write("=" * W + "\n")

    out.write(f"\n{'─' * W}\n")
    out.write("TASK 1: GENERATION FAILURE TAXONOMY\n")
    out.write(f"{'─' * W}\n\n")

    for r in rows:
        r["failure_type"] = classify_failure(r)

    types = Counter(r["failure_type"] for r in rows)
    out.write(f"  Total: {len(rows)} queries, {sum(r['win'] for r in rows)} wins, "
              f"{sum(not r['win'] for r in rows)} regressions\n\n")
    out.write(f"  {'Type':<18} {'Count':>5} {'%':>5}\n")
    out.write("  " + "-" * 30 + "\n")
    for t, c in types.most_common():
        out.write(f"  {t:<18} {c:>5} {100*c/len(rows):>5.0f}%\n")

    # ── TASK 2: ANSWER STRUCTURE SCORES ──
    out.write(f"\n{'─' * W}\n")
    out.write("TASK 2: ANSWER STRUCTURE VALIDATION\n")
    out.write(f"{'─' * W}\n\n")

    out.write(f"  {'QID':>3} {'Win':>4} {'ΔOQ':>4} {'QType':<12} {'Struct':>6} "
              f"{'EntCov':>6} {'Trace':>6} {'Compar':>6} {'Decor':>6} {'Evid':>6} {'Contra':>6} {'Depth':>6} {'Type':<16}\n")
    out.write("  " + "-" * 105 + "\n")

    for r in sorted(rows, key=lambda x: x["validation"]["structure_score"]):
        v = r["validation"]
        d = v["dimensions"]
        win = " ✓" if r["win"] else " ✗"
        out.write(
            f"  {r['query_id']:>3} {win:>4} {r['overall_delta']:>+4.0f} {v['query_type']:<12} "
            f"{v['structure_score']:>6.3f} {d['entity_coverage']:>6.3f} {d['trace_completeness']:>6.3f} "
            f"{d['comparative_structure']:>6.3f} {d['decorator_mention']:>6.3f} {d['evidence_density']:>6.3f} "
            f"{d['contradiction_score']:>6.3f} {d['answer_depth']:>6.3f} {r['failure_type']:<16}\n"
        )

    # Structure score vs outcome
    win_structs = [r["validation"]["structure_score"] for r in rows if r["win"]]
    loss_structs = [r["validation"]["structure_score"] for r in rows if not r["win"]]
    out.write(f"\n  Win mean structure_score:  {sum(win_structs)/len(win_structs):.3f} (n={len(win_structs)})\n")
    out.write(f"  Loss mean structure_score: {sum(loss_structs)/len(loss_structs):.3f} (n={len(loss_structs)})\n")
    out.write(f"  Separation: {sum(win_structs)/len(win_structs) - sum(loss_structs)/len(loss_structs):+.3f}\n")

    # Candidate vs baseline structure comparison
    out.write(f"\n  Candidate vs Baseline structure scores:\n")
    cand_better = 0
    base_better = 0
    for r in rows:
        cs = r["validation"]["structure_score"]
        bs = r["baseline_validation"]["structure_score"]
        if cs > bs + 0.05:
            cand_better += 1
        elif bs > cs + 0.05:
            base_better += 1
    out.write(f"    Candidate structurally better: {cand_better}\n")
    out.write(f"    Baseline structurally better:  {base_better}\n")
    out.write(f"    Comparable:                    {len(rows) - cand_better - base_better}\n")

    # ── TASK 3: GENERATION CONFIDENCE INDEX ──
    out.write(f"\n{'─' * W}\n")
    out.write("TASK 3: GENERATION CONFIDENCE INDEX (GCI)\n")
    out.write(f"{'─' * W}\n\n")

    gci_stats = compute_gci_stats(rows)
    for r in rows:
        v = r["validation"]
        gci, components = compute_gci(
            v["structure_score"],
            v["dimensions"]["evidence_density"],
            v["dimensions"]["answer_depth"],
            v["dimensions"]["contradiction_score"],
            gci_stats,
        )
        r["gci"] = gci
        r["gci_components"] = components

    # CQI_4 computation
    cqi_means, cqi_stds = compute_stats(rows, CQI4_METRICS)
    for r in rows:
        cqi4, ci, rci = compute_cqi4(r, cqi_means, cqi_stds)
        r["cqi4"] = cqi4

    # GCI per query
    out.write(f"  {'QID':>3} {'CQI4':>6} {'GCI':>6} {'Win':>4} {'ΔOQ':>4} {'Zone':<10} {'Type':<16} {'Query':<40}\n")
    out.write("  " + "-" * 95 + "\n")

    for r in sorted(rows, key=lambda x: -x["cqi4"]):
        win = " ✓" if r["win"] else " ✗"
        if r["cqi4"] >= 0.65:
            zone = "HIGH"
        elif r["cqi4"] >= 0.50:
            zone = "GOOD"
        elif r["cqi4"] >= 0.35:
            zone = "AMBIG"
        else:
            zone = "WEAK"
        out.write(
            f"  {r['query_id']:>3} {r['cqi4']:>6.3f} {r['gci']:>6.3f} {win:>4} "
            f"{r['overall_delta']:>+4.0f} {zone:<10} {r['failure_type']:<16} {r['query_text']:<40}\n"
        )

    # GCI correlations
    gci_vals = [r["gci"] for r in rows]
    oq_vals = [r["overall_delta"] for r in rows]
    win_vals = [1.0 if r["win"] else 0.0 for r in rows]
    cqi_vals = [r["cqi4"] for r in rows]

    p_gci_oq = pearson(gci_vals, oq_vals)
    p_gci_win = pearson(gci_vals, win_vals)
    p_cqi_oq = pearson(cqi_vals, oq_vals)
    p_cqi_win = pearson(cqi_vals, win_vals)

    # Combined signal: CQI_4 × GCI
    combined = [c * g for c, g in zip(cqi_vals, gci_vals)]
    p_comb_oq = pearson(combined, oq_vals)
    p_comb_win = pearson(combined, win_vals)

    out.write(f"\n  {'Signal':<20} {'r(OQ)':>8} {'r(win)':>8}\n")
    out.write("  " + "-" * 40 + "\n")
    out.write(f"  {'CQI_4 alone':<20} {p_cqi_oq:>+8.3f} {p_cqi_win:>+8.3f}\n")
    out.write(f"  {'GCI alone':<20} {p_gci_oq:>+8.3f} {p_gci_win:>+8.3f}\n")
    out.write(f"  {'CQI_4 × GCI':<20} {p_comb_oq:>+8.3f} {p_comb_win:>+8.3f}\n")

    # ── TASK 4 SIMULATION: DUAL-PASS CANDIDATES ──
    out.write(f"\n{'─' * W}\n")
    out.write("TASK 4: DUAL-PASS SIMULATION (CQI_4 ≥ 0.50 AND GCI < 0.45)\n")
    out.write(f"{'─' * W}\n\n")

    dual_pass_candidates = [r for r in rows if r["cqi4"] >= 0.50 and r["gci"] < 0.45]
    non_candidates = [r for r in rows if not (r["cqi4"] >= 0.50 and r["gci"] < 0.45)]

    out.write(f"  Queries qualifying for dual-pass: {len(dual_pass_candidates)}/{len(rows)}\n\n")

    if dual_pass_candidates:
        out.write(f"  {'QID':>3} {'CQI4':>6} {'GCI':>6} {'Win':>4} {'ΔOQ':>4} {'Struct':>6} {'Type':<16} {'Query':<40}\n")
        out.write("  " + "-" * 90 + "\n")
        for r in dual_pass_candidates:
            win = " ✓" if r["win"] else " ✗"
            out.write(
                f"  {r['query_id']:>3} {r['cqi4']:>6.3f} {r['gci']:>6.3f} {win:>4} "
                f"{r['overall_delta']:>+4.0f} {r['validation']['structure_score']:>6.3f} "
                f"{r['failure_type']:<16} {r['query_text']:<40}\n"
            )

        dp_wins = sum(1 for r in dual_pass_candidates if r["win"])
        dp_regs = len(dual_pass_candidates) - dp_wins
        out.write(f"\n  Among dual-pass candidates: {dp_wins} wins, {dp_regs} regressions\n")
        out.write(f"  If dual-pass fixed 50% of regressions: +{dp_regs//2} potential wins\n")
        out.write(f"  Projected win rate: {(sum(r['win'] for r in rows) + dp_regs//2)}/{len(rows)} "
                  f"= {100*(sum(r['win'] for r in rows) + dp_regs//2)/len(rows):.0f}%\n")
        out.write(f"  Extra tokens (estimate): ~{sum(r.get('tokens_out',0) for r in dual_pass_candidates)} "
                  f"(+{100*len(dual_pass_candidates)/len(rows):.0f}% queries re-generated)\n")

    # ── EXPERIMENTAL SUMMARY ──
    out.write(f"\n{'=' * W}\n")
    out.write("EXPERIMENTAL SUMMARY\n")
    out.write(f"{'=' * W}\n\n")

    total = len(rows)
    wins = sum(r["win"] for r in rows)

    out.write(f"  Current baseline: {wins}/{total} wins ({100*wins/total:.0f}%)\n\n")

    # Experiment 1: GCI screening only (no regeneration)
    # Flag queries where GCI < 0.45 → would not generate
    gci_blocked = [r for r in rows if r["gci"] < 0.45]
    gci_remaining = [r for r in rows if r["gci"] >= 0.45]
    exp1_wins = sum(r["win"] for r in gci_remaining)
    out.write(f"  Exp 1 (GCI < 0.45 blocked): {exp1_wins}/{len(gci_remaining)} wins "
              f"({100*exp1_wins/max(len(gci_remaining),1):.0f}%) — {len(gci_blocked)} blocked\n")

    # Experiment 2: Dual-pass for CQI≥0.50 + GCI<0.45 (assume 50% fix rate)
    fixable_regs = sum(1 for r in dual_pass_candidates if not r["win"])
    exp2_wins = wins + fixable_regs // 2
    out.write(f"  Exp 2 (dual-pass 50% fix): {exp2_wins}/{total} wins ({100*exp2_wins/total:.0f}%)\n")

    # Experiment 3: CQI_4 < 0.40 blocked + dual-pass for rest
    cqi_blocked = [r for r in rows if r["cqi4"] < 0.40]
    cqi_remaining = [r for r in rows if r["cqi4"] >= 0.40]
    cqi_wins = sum(r["win"] for r in cqi_remaining)
    cqi_dp_candidates = [r for r in cqi_remaining if r["cqi4"] >= 0.50 and r["gci"] < 0.45 and not r["win"]]
    exp3_wins = cqi_wins + len(cqi_dp_candidates) // 2
    out.write(f"  Exp 3 (CQI gate + dual-pass): {exp3_wins}/{len(cqi_remaining)} wins "
              f"({100*exp3_wins/max(len(cqi_remaining),1):.0f}%) — {len(cqi_blocked)} gated\n")

    # Delta analysis
    out.write(f"\n  {'Experiment':<30} {'Win%':>6} {'Δ vs Base':>10} {'Queries':>8} {'Extra Cost':>11}\n")
    out.write("  " + "-" * 70 + "\n")
    out.write(f"  {'Baseline (current)':<30} {100*wins/total:>5.0f}% {'—':>10} {total:>8} {'—':>11}\n")
    out.write(f"  {'Exp 1 (GCI screening)':<30} {100*exp1_wins/max(len(gci_remaining),1):>5.0f}% "
              f"{100*exp1_wins/max(len(gci_remaining),1)-100*wins/total:>+9.0f}pp {len(gci_remaining):>8} {'−saved':>11}\n")
    out.write(f"  {'Exp 2 (dual-pass)':<30} {100*exp2_wins/total:>5.0f}% "
              f"{100*exp2_wins/total-100*wins/total:>+9.0f}pp {total:>8} {f'+{len(dual_pass_candidates)} regen':>11}\n")
    out.write(f"  {'Exp 3 (CQI gate + dual)':<30} {100*exp3_wins/max(len(cqi_remaining),1):>5.0f}% "
              f"{100*exp3_wins/max(len(cqi_remaining),1)-100*wins/total:>+9.0f}pp {len(cqi_remaining):>8} "
              f"{f'+{len(cqi_dp_candidates)} regen':>11}\n")

    out.write(f"\n{'=' * W}\n")


if __name__ == "__main__":
    main()
