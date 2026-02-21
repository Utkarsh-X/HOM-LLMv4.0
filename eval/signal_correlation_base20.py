"""
BASE20 Context Signal Correlation Analysis with Statistical Robustness.

Computes M1-M7 from telemetry, joins with judge deltas, and produces:
- Pearson + Spearman correlations
- Leave-one-out stability analysis
- Bootstrap confidence intervals (1000 resamples)

Usage:
    set PYTHONIOENCODING=utf-8
    python eval/signal_correlation_base20.py --run <run_name>

If --run is not specified, uses the most recent run.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────

EVAL_DIR = Path(__file__).resolve().parent
RUNS_DIR = EVAL_DIR / "runs"

JUDGE_CANDIDATES = [
    "judge_results__gpt-oss-120b.jsonl",
    "judge_results__gemini-2.5-flash.jsonl",
]

JUDGE_DIMS = [
    "overall_quality",
    "semantic_correctness",
    "factual_consistency",
    "completeness",
    "hallucination_risk",
]

METRIC_NAMES = [
    "M1_semantic_strength",
    "M2_query_term_recall",
    "M3_file_entropy",
    "M4_content_overlap",
    "M5_score_separation",
    "M6_reranker_influence",
    "M7_budget_utilization",
]

BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 42


# ──────────────────────────────────────────────────────────────────────────
# METRIC COMPUTATION (from telemetry)
# ──────────────────────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "the", "is", "a", "of", "in", "to", "for", "and", "or", "not", "with",
    "on", "at", "by", "from", "as", "it", "this", "that", "an", "be", "are",
    "was", "were", "been", "do", "does", "did", "has", "have", "had", "will",
    "would", "can", "could", "should", "may", "might", "i", "me", "my", "we",
    "you", "your", "he", "she", "they", "them", "its",
})
_TOKEN_SPLIT = re.compile(r"[^a-z0-9_]+")

def _tokenize(text: str) -> set[str]:
    """Lowercase split, unique terms, stopwords removed."""
    tokens = _TOKEN_SPLIT.split(text.lower())
    return {t for t in tokens if t and len(t) > 1 and t not in _STOPWORDS}

def compute_m1(telemetry: dict) -> float:
    """M1: Mean semantic_score of context blocks.

    Prefers per-block drop_trace data.  Falls back to ranking_geometry
    sigmoid_mean (mean cross-encoder score on the full ranked surface).
    """
    dt = telemetry["phases"]["CONTEXT"].get("drop_trace")
    if dt:
        kept = [b for b in dt if b.get("drop_reason") == "kept"]
        if kept:
            return sum(b["semantic_score"] for b in kept) / len(kept)
    # Fallback: mean cross-encoder sigmoid on ranked surface
    geom = telemetry["phases"]["RANKING"].get("ranking_geometry")
    if geom and "sigmoid_mean" in geom:
        return float(geom["sigmoid_mean"])
    return 0.0


def compute_m2(telemetry: dict, query_text: str) -> float | None:
    """M2: Fraction of query terms found in at least one kept block.

    Requires block_content in drop_trace. Returns None if unavailable.
    """
    dt = telemetry["phases"]["CONTEXT"].get("drop_trace")
    if not dt:
        return None
    kept_contents = [
        b["block_content"] for b in dt
        if b.get("drop_reason") == "kept" and b.get("block_content")
    ]
    if not kept_contents:
        return None
    query_terms = _tokenize(query_text)
    if not query_terms:
        return 0.0
    context_terms: set[str] = set()
    for content in kept_contents:
        context_terms.update(_tokenize(content))
    return len(query_terms & context_terms) / len(query_terms)


def compute_m3(telemetry: dict) -> float:
    """M3: Normalized Shannon entropy of file distribution.

    Prefers per-block drop_trace data.  Falls back to
    signal_profile.file_entropy (ranking-level, full surface).
    """
    dt = telemetry["phases"]["CONTEXT"].get("drop_trace")
    if dt:
        kept = [b for b in dt if b.get("drop_reason") == "kept"]
        if kept:
            files = [b["file"] for b in kept]
            k = len(files)
            counts = Counter(files)
            unique = len(counts)
            if unique <= 1:
                return 0.0
            h = -sum((c / k) * math.log(c / k) for c in counts.values() if c > 0)
            h_max = math.log(unique)
            return h / h_max if h_max > 0 else 0.0
    # Fallback: ranking signal_profile file_entropy
    sp = telemetry["phases"]["RANKING"].get("signal_profile")
    if sp and "file_entropy" in sp:
        return float(sp["file_entropy"])
    return 0.0


def compute_m4(telemetry: dict) -> float | None:
    """M4: Mean pairwise Jaccard similarity among kept blocks.

    Requires block_content in drop_trace. Returns None if unavailable.
    """
    dt = telemetry["phases"]["CONTEXT"].get("drop_trace")
    if not dt:
        return None
    kept_contents = [
        b["block_content"] for b in dt
        if b.get("drop_reason") == "kept" and b.get("block_content")
    ]
    k = len(kept_contents)
    if k <= 1:
        return 0.0 if k == 1 else None
    token_sets = [_tokenize(c) for c in kept_contents]
    total_j = 0.0
    pairs = 0
    for i in range(k):
        for j in range(i + 1, k):
            union = token_sets[i] | token_sets[j]
            if not union:
                continue
            total_j += len(token_sets[i] & token_sets[j]) / len(union)
            pairs += 1
    return total_j / pairs if pairs > 0 else 0.0


def compute_m5(telemetry: dict) -> float:
    """M5: CV of final_score across ALL candidates (full ranked surface).

    Prefers per-block drop_trace data.  Falls back to
    signal_profile.score_variance + candidate count to estimate CV.
    """
    dt = telemetry["phases"]["CONTEXT"].get("drop_trace")
    if dt:
        scores = [b["final_score"] for b in dt]
        n = len(scores)
        mu = sum(scores) / n if n > 0 else 0.0
        if abs(mu) < 1e-10 or n == 0:
            return 0.0
        var = sum((s - mu) ** 2 for s in scores) / n
        return math.sqrt(var) / abs(mu)
    # Fallback: use ranking_geometry final_score_variance
    geom = telemetry["phases"]["RANKING"].get("ranking_geometry")
    sp = telemetry["phases"]["RANKING"].get("signal_profile")
    if geom and "final_score_variance" in geom:
        var = float(geom["final_score_variance"])
        # Estimate mean from base_variance + alpha contributions
        # The score_variance from signal_profile is base_score variance
        # final mean is typically around 0.5-0.8 range
        # Use total candidates + variance to estimate CV
        n_cand = int(telemetry["phases"]["RANKING"].get("candidates", 1))
        # We need the mean; approximate from variance + known score range
        # For a better estimate, use: mean ~ sqrt(variance) / CV_known ≈ 0.5
        # Rather than guessing, store sqrt(var) directly as a spread proxy
        sigma = math.sqrt(var) if var > 0 else 0.0
        # Approximate mean from base and rerank means if available
        if sp and "score_variance" in sp:
            base_var = float(sp["score_variance"])
            # We know final = base + alpha * rerank_delta + gamma * struct
            # Approximate final_mean ≈ base_mean ≈ 0.5 (typical)
            # But better to compute from actual telemetry if available
            pass
        # Use a heuristic: if sigmoid_mean is the CE mean, final_mean ≈ base_mean + sigmoid_mean * alpha
        # Since we don't know base_mean exactly, just return sigma as a scalar proxy
        # This is still valid for correlation (monotonic transform of spread)
        return sigma
    return 0.0


def compute_m6(telemetry: dict) -> float:
    """M6: From ranking_geometry telemetry (full ranked surface)."""
    geom = telemetry["phases"]["RANKING"].get("ranking_geometry")
    if geom and "rerank_contribution_percent" in geom:
        return float(geom["rerank_contribution_percent"]) / 100.0
    return 0.0


def compute_m7(telemetry: dict) -> float:
    """M7: used_tokens / token_budget."""
    ctx = telemetry["phases"]["CONTEXT"]
    budget = ctx.get("token_budget", 0)
    used = ctx.get("tokens", 0)
    return used / budget if budget > 0 else 0.0


def compute_all_metrics(telemetry: dict, query_text: str = "") -> dict[str, float | None]:
    return {
        "M1_semantic_strength": compute_m1(telemetry),
        "M2_query_term_recall": compute_m2(telemetry, query_text),
        "M3_file_entropy": compute_m3(telemetry),
        "M4_content_overlap": compute_m4(telemetry),
        "M5_score_separation": compute_m5(telemetry),
        "M6_reranker_influence": compute_m6(telemetry),
        "M7_budget_utilization": compute_m7(telemetry),
    }


# ──────────────────────────────────────────────────────────────────────────
# STATISTICS
# ──────────────────────────────────────────────────────────────────────────

def pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / n)
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / n)
    if sx < 1e-15 or sy < 1e-15:
        return 0.0
    return cov / (sx * sy)


def _rank(vals: list[float]) -> list[float]:
    n = len(vals)
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


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return 0.0
    return pearson(_rank(x), _rank(y))


def loo_stability(x: list[float], y: list[float]) -> dict:
    """Leave-one-out stability: drop each observation, recompute pearson."""
    n = len(x)
    if n < 4:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "range": 0.0}
    loo_corrs = []
    for i in range(n):
        xi = x[:i] + x[i + 1:]
        yi = y[:i] + y[i + 1:]
        loo_corrs.append(pearson(xi, yi))
    mean_c = sum(loo_corrs) / len(loo_corrs)
    std_c = math.sqrt(sum((c - mean_c) ** 2 for c in loo_corrs) / len(loo_corrs))
    return {
        "mean": mean_c,
        "std": std_c,
        "min": min(loo_corrs),
        "max": max(loo_corrs),
        "range": max(loo_corrs) - min(loo_corrs),
        "values": loo_corrs,
    }


def bootstrap_ci(x: list[float], y: list[float], n_boot: int = 1000,
                 seed: int = 42, alpha: float = 0.05) -> dict:
    """Bootstrap confidence interval for Pearson correlation."""
    n = len(x)
    if n < 4:
        return {"lo": 0.0, "hi": 0.0, "median": 0.0}
    rng = random.Random(seed)
    boot_corrs = []
    for _ in range(n_boot):
        indices = [rng.randint(0, n - 1) for _ in range(n)]
        bx = [x[i] for i in indices]
        by = [y[i] for i in indices]
        boot_corrs.append(pearson(bx, by))
    boot_corrs.sort()
    lo_idx = int(n_boot * alpha / 2)
    hi_idx = int(n_boot * (1 - alpha / 2))
    return {
        "lo": boot_corrs[lo_idx],
        "hi": boot_corrs[hi_idx],
        "median": boot_corrs[n_boot // 2],
        "mean": sum(boot_corrs) / n_boot,
    }


def zscore_normalize(values: list[float]) -> list[float]:
    n = len(values)
    if n < 2:
        return [0.0] * n
    mu = sum(values) / n
    s = math.sqrt(sum((v - mu) ** 2 for v in values) / (n - 1))
    if s < 1e-15:
        return [0.0] * n
    return [(v - mu) / s for v in values]


# ──────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────────────────────────────────

def find_latest_run() -> Path:
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name.startswith("run_")])
    if not runs:
        raise FileNotFoundError("No runs found in eval/runs/")
    return runs[-1]


def find_judge_file(run_dir: Path) -> Path:
    for name in JUDGE_CANDIDATES:
        path = run_dir / name
        if path.exists():
            return path
    raise FileNotFoundError(f"No judge file found in {run_dir}")


def load_responses(run_dir: Path) -> list[dict]:
    path = run_dir / "responses.jsonl"
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_judge(path: Path) -> dict[int, dict]:
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                j = json.loads(line)
                result[j["query_id"]] = j
    return result


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Context signal correlation with bootstrap CIs and LOO stability.")
    parser.add_argument("--run", type=str, help="Run name (default: latest)")
    parser.add_argument("--judge-file", type=str, help="Judge results filename override")
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP_N, help="Number of bootstrap resamples")
    args = parser.parse_args()

    # Resolve run directory
    if args.run:
        run_dir = RUNS_DIR / args.run
    else:
        run_dir = find_latest_run()

    if not run_dir.exists():
        print(f"ERROR: Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    # Find judge file
    if args.judge_file:
        judge_path = run_dir / args.judge_file
    else:
        judge_path = find_judge_file(run_dir)

    # Load data
    responses = load_responses(run_dir)
    judge_results = load_judge(judge_path)

    # Build data rows
    rows = []
    skipped = 0
    for resp in responses:
        qid = resp["query_id"]
        tpath = resp.get("telemetry_path", "")
        if not tpath or not os.path.exists(tpath):
            skipped += 1
            continue
        telemetry = json.load(open(tpath, "r", encoding="utf-8"))
        metrics = compute_all_metrics(telemetry, query_text=resp.get("query_text", ""))

        if qid not in judge_results:
            skipped += 1
            continue

        scores = judge_results[qid]["scores"]
        deltas = {}
        for dim in JUDGE_DIMS:
            if dim in scores:
                deltas[dim] = scores[dim]["candidate"] - scores[dim]["baseline"]

        rows.append({"query_id": qid, "query_text": resp.get("query_text", ""), **metrics, **{f"delta_{d}": v for d, v in deltas.items()}})

    n = len(rows)

    # ──────────────────────────────────────────────────────────────────
    # REPORT
    # ──────────────────────────────────────────────────────────────────

    out = sys.stdout
    W = 90

    out.write("\n" + "=" * W + "\n")
    out.write("CONTEXT SIGNAL CORRELATION — BASE20 ANALYSIS\n")
    out.write(f"Run: {run_dir.name}\n")
    out.write(f"Judge: {judge_path.name}\n")
    out.write(f"Queries: {n} (skipped: {skipped})\n")
    out.write(f"Bootstrap resamples: {args.bootstrap}\n")
    out.write("=" * W + "\n\n")

    if n < 4:
        out.write(f"ERROR: Only {n} data points. Need >= 4 for analysis.\n")
        sys.exit(1)

    # Determine which metrics are available (not all-None)
    available_metrics = []
    for m in METRIC_NAMES:
        has_value = any(row.get(m) is not None for row in rows)
        available_metrics.append(m)
        if not has_value:
            out.write(f"  [NOTE] {m}: all None (block_content not in telemetry)\n")
        # Coerce None -> 0.0 for display and computation
        for row in rows:
            if row.get(m) is None:
                row[m] = 0.0

    # Metrics with real data (not all zeros from None coercion)
    active_metrics = [m for m in METRIC_NAMES if any(row[m] != 0.0 for row in rows)]

    # RAW DATA TABLE
    out.write("--- RAW DATA ---\n")
    header = f"{'qid':>4}"
    for m in METRIC_NAMES:
        out.write("")
        header += f" {m[3:]:>16}"
    for d in JUDGE_DIMS:
        header += f" {'d_' + d[:12]:>14}"
    out.write(header + "\n")
    for row in rows:
        line = f"{row['query_id']:>4}"
        for m in METRIC_NAMES:
            line += f" {row[m]:>16.4f}"
        for d in JUDGE_DIMS:
            line += f" {row.get(f'delta_{d}', 0):>14.0f}"
        out.write(line + "\n")

    # DESCRIPTIVE STATS
    out.write(f"\n--- METRIC DESCRIPTIVE STATISTICS (n={n}) ---\n")
    out.write(f"{'Metric':<25} {'min':>8} {'max':>8} {'mean':>8} {'std':>8}\n")
    for m in METRIC_NAMES:
        vals = [row[m] for row in rows]
        mn, mx = min(vals), max(vals)
        avg = sum(vals) / len(vals)
        std = math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals))
        out.write(f"{m:<25} {mn:>8.4f} {mx:>8.4f} {avg:>8.4f} {std:>8.4f}\n")

    # CORRELATIONS
    out.write(f"\n--- CORRELATIONS (Pearson / Spearman) ---\n")
    if n < 10:
        out.write(f"!! WARNING: n={n} is small. Interpret with caution.\n\n")

    results = []
    for m in active_metrics:
        m_vals = [row[m] for row in rows]
        for dim in JUDGE_DIMS:
            d_vals = [row.get(f"delta_{dim}", 0) for row in rows]
            p = pearson(m_vals, d_vals)
            s = spearman(m_vals, d_vals)
            loo = loo_stability(m_vals, d_vals)
            bci = bootstrap_ci(m_vals, d_vals, n_boot=args.bootstrap, seed=BOOTSTRAP_SEED)
            results.append({
                "metric": m, "dim": dim,
                "pearson": p, "spearman": s,
                "abs_p": abs(p),
                "loo_mean": loo["mean"], "loo_std": loo["std"],
                "loo_range": loo["range"],
                "boot_lo": bci["lo"], "boot_hi": bci["hi"], "boot_median": bci["median"],
            })

    results.sort(key=lambda r: r["abs_p"], reverse=True)

    out.write(f"{'Metric':<22} {'Judge Dim':<18} {'Pear':>6} {'Spear':>7} {'LOO_m':>7} {'LOO_s':>7} {'95%CI_lo':>9} {'95%CI_hi':>9} {'Sig':>8}\n")
    out.write("-" * W + "\n")
    for r in results:
        ap = r["abs_p"]
        sig = "STRONG" if ap >= 0.5 else ("MODER" if ap >= 0.35 else ("weak" if ap >= 0.2 else "-"))
        out.write(
            f"{r['metric']:<22} {r['dim']:<18} {r['pearson']:>+6.3f} {r['spearman']:>+7.3f} "
            f"{r['loo_mean']:>+7.3f} {r['loo_std']:>7.3f} [{r['boot_lo']:>+7.3f}, {r['boot_hi']:>+7.3f}] "
            f"{sig:>8}\n"
        )

    # COMPOSITE (unweighted z-score sum)
    out.write(f"\n--- COMPOSITE (unweighted z-score sum) ---\n")
    zscored = {m: zscore_normalize([row[m] for row in rows]) for m in METRIC_NAMES}
    composite = [sum(zscored[m][i] for m in METRIC_NAMES) for i in range(n)]

    for dim in JUDGE_DIMS:
        d_vals = [row.get(f"delta_{dim}", 0) for row in rows]
        p = pearson(composite, d_vals)
        s = spearman(composite, d_vals)
        bci = bootstrap_ci(composite, d_vals, n_boot=args.bootstrap, seed=BOOTSTRAP_SEED)
        sig = "STRONG" if abs(p) >= 0.5 else ("MODER" if abs(p) >= 0.35 else "-")
        out.write(f"  composite x {dim:<22} Pearson={p:>+.3f} Spearman={s:>+.3f} 95%CI=[{bci['lo']:>+.3f}, {bci['hi']:>+.3f}] {sig}\n")

    # LOO STABILITY SUMMARY
    out.write(f"\n--- LEAVE-ONE-OUT STABILITY ---\n")
    out.write(f"{'Metric':<22} {'Judge Dim':<18} {'Full_r':>7} {'LOO_mean':>9} {'LOO_std':>8} {'LOO_range':>10} {'Stable?':>8}\n")
    out.write("-" * W + "\n")
    # Show top 10 by |pearson|
    for r in results[:15]:
        stable = "YES" if r["loo_std"] < 0.15 and r["loo_range"] < 0.4 else "FRAGILE"
        out.write(
            f"{r['metric']:<22} {r['dim']:<18} {r['pearson']:>+7.3f} {r['loo_mean']:>+9.3f} "
            f"{r['loo_std']:>8.3f} {r['loo_range']:>10.3f} {stable:>8}\n"
        )

    # BOOTSTRAP CI SUMMARY
    out.write(f"\n--- BOOTSTRAP 95% CONFIDENCE INTERVALS ---\n")
    out.write(f"{'Metric':<22} {'Judge Dim':<18} {'Pearson':>8} {'CI_lower':>9} {'CI_upper':>9} {'Width':>7} {'Excludes 0?':>12}\n")
    out.write("-" * W + "\n")
    for r in results[:15]:
        width = r["boot_hi"] - r["boot_lo"]
        excludes_zero = "YES" if (r["boot_lo"] > 0 or r["boot_hi"] < 0) else "no"
        out.write(
            f"{r['metric']:<22} {r['dim']:<18} {r['pearson']:>+8.3f} {r['boot_lo']:>+9.3f} {r['boot_hi']:>+9.3f} "
            f"{width:>7.3f} {excludes_zero:>12}\n"
        )

    # SUMMARY
    out.write(f"\n{'=' * W}\n")
    out.write("SUMMARY\n")
    out.write(f"{'=' * W}\n\n")

    strong = [r for r in results if r["abs_p"] >= 0.5]
    moderate = [r for r in results if 0.35 <= r["abs_p"] < 0.5]

    # Strong + stable
    strong_stable = [r for r in strong if r["loo_std"] < 0.15]
    strong_fragile = [r for r in strong if r["loo_std"] >= 0.15]

    if strong_stable:
        out.write(f"STRONG & STABLE ({len(strong_stable)}):\n")
        for r in strong_stable:
            d = "pos" if r["pearson"] > 0 else "NEG"
            out.write(f"  {r['metric']} x {r['dim']}: r={r['pearson']:+.3f} LOO_std={r['loo_std']:.3f} CI=[{r['boot_lo']:+.3f},{r['boot_hi']:+.3f}] ({d})\n")

    if strong_fragile:
        out.write(f"\nSTRONG but FRAGILE ({len(strong_fragile)}):\n")
        for r in strong_fragile:
            out.write(f"  {r['metric']} x {r['dim']}: r={r['pearson']:+.3f} LOO_std={r['loo_std']:.3f} range={r['loo_range']:.3f}\n")

    if moderate:
        out.write(f"\nMODERATE ({len(moderate)}):\n")
        for r in moderate:
            out.write(f"  {r['metric']} x {r['dim']}: r={r['pearson']:+.3f}\n")

    near_zero = len([r for r in results if r["abs_p"] < 0.15])
    out.write(f"\nNear-zero: {near_zero}/{len(results)}\n")
    # Check if M2/M4 were available
    m2_available = any(row.get("M2_query_term_recall") is not None for row in rows)
    m4_available = any(row.get("M4_content_overlap") is not None for row in rows)
    if not m2_available or not m4_available:
        missing = []
        if not m2_available: missing.append("M2 (query_term_recall)")
        if not m4_available: missing.append("M4 (content_overlap)")
        out.write(f"\nNOT AVAILABLE: {', '.join(missing)} — block_content not in drop_trace for this run\n")

    # VERDICT
    out.write(f"\n{'=' * W}\n")
    max_r = max(r["abs_p"] for r in results) if results else 0.0
    stable_strong = [r for r in results if r["abs_p"] >= 0.5 and r["loo_std"] < 0.15]
    if stable_strong:
        out.write(f"VERDICT: Case A — Strong, stable predictive signal found (max |r| = {max_r:.3f})\n")
        out.write(f"         {len(stable_strong)} metric-dimension pairs are strong AND stable.\n")
    elif strong:
        out.write(f"VERDICT: Case A (fragile) — Strong signals found but LOO stability is poor (max |r| = {max_r:.3f})\n")
        out.write(f"         Need more data to confirm.\n")
    elif max_r >= 0.35:
        out.write(f"VERDICT: Case B — Moderate mixed signals (max |r| = {max_r:.3f})\n")
    else:
        out.write(f"VERDICT: Case C — Weak correlation (max |r| = {max_r:.3f})\n")
    out.write(f"{'=' * W}\n")


if __name__ == "__main__":
    main()
