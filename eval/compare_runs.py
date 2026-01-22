"""Run-to-run delta comparison for HOM-LLM evaluations.

Loads judge outputs from two runs and reports directional deltas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def read_jsonl(path: Path) -> List[Dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_scores(path: Path) -> Dict[int, Dict]:
    records = read_jsonl(path)
    return {r["query_id"]: r for r in records}


def delta(a: float, b: float) -> float:
    return b - a


def summarize(a_scores: Dict[int, Dict], b_scores: Dict[int, Dict]) -> Tuple[List[Dict], float]:
    rows = []
    deltas = []
    for qid, a_rec in a_scores.items():
        b_rec = b_scores.get(qid)
        if not b_rec:
            continue
        a_overall = float(a_rec.get("scores", {}).get("overall_quality", 0))
        b_overall = float(b_rec.get("scores", {}).get("overall_quality", 0))
        d = delta(a_overall, b_overall)
        deltas.append(d)
        rows.append(
            {
                "query_id": qid,
                "a_overall": a_overall,
                "b_overall": b_overall,
                "delta": d,
                "verdict_a": a_rec.get("verdict"),
                "verdict_b": b_rec.get("verdict"),
            }
        )
    aggregate = sum(deltas) / len(deltas) if deltas else 0.0
    return rows, aggregate


def write_csv(rows: List[Dict], path: Path) -> None:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["query_id", "a_overall", "b_overall", "delta", "verdict_a", "verdict_b"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: List[Dict], aggregate: float, path: Path, run_a: str, run_b: str) -> None:
    lines = [
        f"# Delta Report: {run_a} → {run_b}",
        "",
        f"- Average overall delta: {aggregate:+.2f}",
        "",
        "| Query | Overall A | Overall B | Δ | Verdict A | Verdict B |",
        "|-------|-----------|-----------|----|-----------|-----------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['query_id']:02d} | {row['a_overall']:.2f} | {row['b_overall']:.2f} | "
            f"{row['delta']:+.2f} | {row.get('verdict_a','')} | {row.get('verdict_b','')} |"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare judge results between two runs.")
    parser.add_argument("--a", type=str, required=True, help="Run name or path for baseline (older) run")
    parser.add_argument("--b", type=str, required=True, help="Run name or path for new run")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("eval/runs"),
        help="Base directory containing run folders",
    )
    args = parser.parse_args()

    run_a_dir = Path(args.a)
    if not run_a_dir.exists():
        run_a_dir = args.runs_dir / args.a
    run_b_dir = Path(args.b)
    if not run_b_dir.exists():
        run_b_dir = args.runs_dir / args.b

    a_scores = load_scores(run_a_dir / "judge_results.jsonl")
    b_scores = load_scores(run_b_dir / "judge_results.jsonl")

    rows, aggregate = summarize(a_scores, b_scores)

    out_dir = args.runs_dir / f"compare_{run_a_dir.name}_vs_{run_b_dir.name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "delta.csv"
    md_path = out_dir / "delta.md"
    write_csv(rows, csv_path)
    write_markdown(rows, aggregate, md_path, run_a_dir.name, run_b_dir.name)

    print(f"Wrote delta CSV: {csv_path}")
    print(f"Wrote delta Markdown: {md_path}")
    print(f"Average overall delta: {aggregate:+.2f}")


if __name__ == "__main__":
    main()
