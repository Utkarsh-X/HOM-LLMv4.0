"""Aggregate repeated judge results across multiple eval runs.

Purpose:
- reduce overreaction to a single noisy judged run
- summarize majority verdicts per query across repeated runs
- report stability / volatility so promotion decisions use aggregated evidence

Inputs:
- one or more run names under eval/runs, or direct run directory paths
- each run directory must contain a judge_results__*.jsonl file

Outputs:
- console summary
- optional markdown report
- optional csv with per-query aggregation
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


VERDICT_ORDER = ("improved", "equal", "regressed")
METRIC_ORDER = (
    "semantic_correctness",
    "factual_consistency",
    "completeness",
    "clarity",
    "relevance",
    "hallucination_risk",
    "verbosity",
    "overall_quality",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _resolve_run_dir(run_arg: str, runs_dir: Path) -> Path:
    candidate = Path(run_arg)
    if candidate.exists():
        return candidate.resolve()
    return (runs_dir / run_arg).resolve()


def _find_judge_file(run_dir: Path) -> Path:
    candidates = sorted(run_dir.glob("judge_results__*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No judge_results__*.jsonl found in {run_dir}")
    return candidates[0]


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(mean(values))


def _format_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _majority_verdict(counter: Counter[str]) -> str:
    best_label = "equal"
    best_count = -1
    for label in VERDICT_ORDER:
        count = counter.get(label, 0)
        if count > best_count:
            best_label = label
            best_count = count
    return best_label


def _aggregate_runs(run_dirs: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    per_query: dict[int, dict[str, Any]] = {}
    run_names: list[str] = []

    for run_dir in run_dirs:
        run_names.append(run_dir.name)
        judge_file = _find_judge_file(run_dir)
        for row in _read_jsonl(judge_file):
            qid = int(row["query_id"])
            bucket = per_query.setdefault(
                qid,
                {
                    "query_id": qid,
                    "query_text": row.get("query_text", ""),
                    "runs_present": [],
                    "verdicts": [],
                    "scores": defaultdict(list),
                    "candidate_overall_scores": [],
                    "baseline_overall_scores": [],
                },
            )
            verdict = str(row.get("verdict", "")).strip().lower()
            bucket["runs_present"].append(run_dir.name)
            bucket["verdicts"].append(verdict)

            scores = row.get("scores", {}) or {}
            for metric in METRIC_ORDER:
                metric_row = scores.get(metric) or {}
                cand = metric_row.get("candidate")
                base = metric_row.get("baseline")
                if cand is not None:
                    bucket["scores"][f"{metric}_candidate"].append(float(cand))
                if base is not None:
                    bucket["scores"][f"{metric}_baseline"].append(float(base))
                if metric == "overall_quality":
                    if cand is not None:
                        bucket["candidate_overall_scores"].append(float(cand))
                    if base is not None:
                        bucket["baseline_overall_scores"].append(float(base))

    rows: list[dict[str, Any]] = []
    overall_verdict_counts = Counter()
    stable_queries = 0
    volatile_queries = 0

    for qid in sorted(per_query):
        bucket = per_query[qid]
        verdict_counter = Counter(bucket["verdicts"])
        majority = _majority_verdict(verdict_counter)
        unique_verdicts = len([v for v in VERDICT_ORDER if verdict_counter.get(v, 0) > 0])
        stable = unique_verdicts == 1
        if stable:
            stable_queries += 1
        else:
            volatile_queries += 1
        overall_verdict_counts[majority] += 1

        candidate_overall_mean = _safe_mean(bucket["candidate_overall_scores"])
        baseline_overall_mean = _safe_mean(bucket["baseline_overall_scores"])
        overall_delta = None
        if candidate_overall_mean is not None and baseline_overall_mean is not None:
            overall_delta = candidate_overall_mean - baseline_overall_mean

        row: dict[str, Any] = {
            "query_id": qid,
            "query_text": bucket["query_text"],
            "runs_seen": len(bucket["runs_present"]),
            "majority_verdict": majority,
            "stable": stable,
            "improved_count": verdict_counter.get("improved", 0),
            "equal_count": verdict_counter.get("equal", 0),
            "regressed_count": verdict_counter.get("regressed", 0),
            "candidate_overall_mean": candidate_overall_mean,
            "baseline_overall_mean": baseline_overall_mean,
            "overall_delta_mean": overall_delta,
        }
        for metric in METRIC_ORDER:
            row[f"{metric}_candidate_mean"] = _safe_mean(bucket["scores"][f"{metric}_candidate"])
            row[f"{metric}_baseline_mean"] = _safe_mean(bucket["scores"][f"{metric}_baseline"])
        rows.append(row)

    summary = {
        "runs": run_names,
        "run_count": len(run_names),
        "query_count": len(rows),
        "majority_improved": overall_verdict_counts.get("improved", 0),
        "majority_equal": overall_verdict_counts.get("equal", 0),
        "majority_regressed": overall_verdict_counts.get("regressed", 0),
        "stable_queries": stable_queries,
        "volatile_queries": volatile_queries,
        "candidate_overall_mean": _safe_mean(
            [r["candidate_overall_mean"] for r in rows if r["candidate_overall_mean"] is not None]
        ),
        "baseline_overall_mean": _safe_mean(
            [r["baseline_overall_mean"] for r in rows if r["baseline_overall_mean"] is not None]
        ),
        "overall_delta_mean": _safe_mean(
            [r["overall_delta_mean"] for r in rows if r["overall_delta_mean"] is not None]
        ),
    }
    return rows, summary


def _write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "query_id",
        "query_text",
        "runs_seen",
        "majority_verdict",
        "stable",
        "improved_count",
        "equal_count",
        "regressed_count",
        "candidate_overall_mean",
        "baseline_overall_mean",
        "overall_delta_mean",
    ]
    fieldnames.extend(f"{metric}_candidate_mean" for metric in METRIC_ORDER)
    fieldnames.extend(f"{metric}_baseline_mean" for metric in METRIC_ORDER)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(rows: list[dict[str, Any]], summary: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Judge Aggregation Report",
        "",
        f"- Runs: {', '.join(summary['runs'])}",
        f"- Run count: {summary['run_count']}",
        f"- Query count: {summary['query_count']}",
        f"- Majority improved: {summary['majority_improved']}",
        f"- Majority equal: {summary['majority_equal']}",
        f"- Majority regressed: {summary['majority_regressed']}",
        f"- Stable queries: {summary['stable_queries']}",
        f"- Volatile queries: {summary['volatile_queries']}",
        f"- Mean candidate overall: {_format_float(summary['candidate_overall_mean'])}",
        f"- Mean baseline overall: {_format_float(summary['baseline_overall_mean'])}",
        f"- Mean overall delta: {_format_float(summary['overall_delta_mean'])}",
        "",
        "## Per-Query Majority",
        "",
        "| Query | Majority | I | = | R | Stable | Candidate Mean | Baseline Mean | Delta |",
        "|------:|----------|---:|---:|---:|:------:|---------------:|--------------:|------:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['query_id']:02d} | {row['majority_verdict']} | {row['improved_count']} | "
            f"{row['equal_count']} | {row['regressed_count']} | "
            f"{'yes' if row['stable'] else 'no'} | "
            f"{_format_float(row['candidate_overall_mean'])} | "
            f"{_format_float(row['baseline_overall_mean'])} | "
            f"{_format_float(row['overall_delta_mean'])} |"
        )

    volatile = [r for r in rows if not r["stable"]]
    if volatile:
        lines.extend(
            [
                "",
                "## Volatile Queries",
                "",
                "| Query | Majority | I | = | R |",
                "|------:|----------|---:|---:|---:|",
            ]
        )
        for row in volatile:
            lines.append(
                f"| {row['query_id']:02d} | {row['majority_verdict']} | {row['improved_count']} | "
                f"{row['equal_count']} | {row['regressed_count']} |"
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate repeated judge results across multiple runs.")
    parser.add_argument(
        "--runs",
        nargs="+",
        required=True,
        help="Run names under eval/runs or direct run directory paths.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("eval/runs"),
        help="Base directory containing run folders.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        help="Optional markdown report path.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Optional CSV path.",
    )
    args = parser.parse_args()

    run_dirs = [_resolve_run_dir(run_arg, args.runs_dir) for run_arg in args.runs]
    for run_dir in run_dirs:
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

    rows, summary = _aggregate_runs(run_dirs)

    print("Judge Aggregation Summary")
    print(f"Runs                : {', '.join(summary['runs'])}")
    print(f"Run count           : {summary['run_count']}")
    print(f"Query count         : {summary['query_count']}")
    print(f"Majority improved   : {summary['majority_improved']}")
    print(f"Majority equal      : {summary['majority_equal']}")
    print(f"Majority regressed  : {summary['majority_regressed']}")
    print(f"Stable queries      : {summary['stable_queries']}")
    print(f"Volatile queries    : {summary['volatile_queries']}")
    print(f"Candidate overall   : {_format_float(summary['candidate_overall_mean'])}")
    print(f"Baseline overall    : {_format_float(summary['baseline_overall_mean'])}")
    print(f"Mean overall delta  : {_format_float(summary['overall_delta_mean'])}")

    if args.output_md:
        _write_markdown(rows, summary, args.output_md)
        print(f"Wrote markdown report: {args.output_md}")
    if args.output_csv:
        _write_csv(rows, args.output_csv)
        print(f"Wrote CSV report: {args.output_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
