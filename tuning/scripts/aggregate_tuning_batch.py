#!/usr/bin/env python3
"""Deterministic aggregation over tuning batch outputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

VERDICT_ORDER = ("improved", "equal", "regressed")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(mean(values))


def _majority_verdict(counter: Counter[str]) -> str:
    best_label = "equal"
    best_count = -1
    for label in VERDICT_ORDER:
        count = counter.get(label, 0)
        if count > best_count:
            best_label = label
            best_count = count
    return best_label


def _aggregate_judge_outputs(paths: list[Path]) -> dict[str, Any]:
    per_query: dict[int, dict[str, Any]] = {}

    for path in paths:
        for row in _read_jsonl(path):
            query_id = int(row["query_id"])
            bucket = per_query.setdefault(
                query_id,
                {
                    "verdicts": [],
                    "candidate_overall": [],
                    "baseline_overall": [],
                },
            )
            bucket["verdicts"].append(str(row.get("verdict", "")).strip().lower())
            scores = row.get("scores", {}) or {}
            overall = scores.get("overall_quality") or {}
            if overall.get("candidate") is not None:
                bucket["candidate_overall"].append(float(overall["candidate"]))
            if overall.get("baseline") is not None:
                bucket["baseline_overall"].append(float(overall["baseline"]))

    majority_counts = Counter()
    stable_queries = 0
    volatile_queries = 0
    per_query_rows: list[dict[str, Any]] = []

    for query_id in sorted(per_query):
        bucket = per_query[query_id]
        verdict_counter = Counter(bucket["verdicts"])
        majority = _majority_verdict(verdict_counter)
        unique_verdicts = len([label for label in VERDICT_ORDER if verdict_counter.get(label, 0) > 0])
        stable = unique_verdicts == 1
        if stable:
            stable_queries += 1
        else:
            volatile_queries += 1
        majority_counts[majority] += 1
        per_query_rows.append(
            {
                "query_id": query_id,
                "majority_verdict": majority,
                "stable": stable,
                "candidate_overall_mean": _safe_mean(bucket["candidate_overall"]),
                "baseline_overall_mean": _safe_mean(bucket["baseline_overall"]),
            }
        )

    candidate_means = [row["candidate_overall_mean"] for row in per_query_rows if row["candidate_overall_mean"] is not None]
    baseline_means = [row["baseline_overall_mean"] for row in per_query_rows if row["baseline_overall_mean"] is not None]
    candidate_overall_mean = _safe_mean(candidate_means)
    baseline_overall_mean = _safe_mean(baseline_means)
    overall_delta_mean = None
    if candidate_overall_mean is not None and baseline_overall_mean is not None:
        overall_delta_mean = candidate_overall_mean - baseline_overall_mean

    return {
        "judge_pass_count": len(paths),
        "query_count": len(per_query_rows),
        "majority_improved": majority_counts.get("improved", 0),
        "majority_equal": majority_counts.get("equal", 0),
        "majority_regressed": majority_counts.get("regressed", 0),
        "stable_queries": stable_queries,
        "volatile_queries": volatile_queries,
        "candidate_overall_mean": candidate_overall_mean,
        "baseline_overall_mean": baseline_overall_mean,
        "overall_delta_mean": overall_delta_mean,
    }


def _format_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate a tuning batch manifest.")
    parser.add_argument("--batch", type=Path, required=True, help="Path to batch_manifest.json")
    parser.add_argument("--output-md", type=Path, help="Optional markdown summary output path")
    parser.add_argument("--output-csv", type=Path, help="Optional csv summary output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    batch_path = args.batch.resolve()
    batch = _read_json(batch_path)

    rows: list[dict[str, Any]] = []
    for experiment in batch.get("experiments", []):
        experiment_name = experiment["name"]
        for generation_run in experiment.get("generation_runs", []):
            judge_groups: dict[str, list[Path]] = {}
            for judge_run in generation_run.get("judge_runs", []):
                judge_name = judge_run["judge_target"]
                judge_groups.setdefault(judge_name, []).append(Path(judge_run["output_path"]))

            for judge_name, output_paths in judge_groups.items():
                summary = _aggregate_judge_outputs(output_paths)
                rows.append(
                    {
                        "experiment": experiment_name,
                        "group": experiment.get("group"),
                        "generation_target": generation_run.get("generation_target"),
                        "generation_index": generation_run.get("generation_index"),
                        "judge_target": judge_name,
                        **summary,
                    }
                )

    rows.sort(
        key=lambda row: (
            -(row.get("overall_delta_mean") or -999.0),
            row.get("majority_regressed", 999),
            -row.get("majority_improved", 0),
        )
    )

    if args.output_csv:
        output_csv = args.output_csv.resolve() if args.output_csv.is_absolute() else (batch_path.parent / args.output_csv).resolve()
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "experiment",
                    "group",
                    "generation_target",
                    "generation_index",
                    "judge_target",
                    "judge_pass_count",
                    "query_count",
                    "majority_improved",
                    "majority_equal",
                    "majority_regressed",
                    "stable_queries",
                    "volatile_queries",
                    "candidate_overall_mean",
                    "baseline_overall_mean",
                    "overall_delta_mean",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    if args.output_md:
        output_md = args.output_md.resolve() if args.output_md.is_absolute() else (batch_path.parent / args.output_md).resolve()
        output_md.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Tuning Batch Summary",
            "",
            f"- Batch: {batch.get('batch_name')}",
            f"- Manifest: {batch_path}",
            "",
            "| Experiment | Group | Gen Target | G# | Judge | I | = | R | Stable | Volatile | Delta |",
            "|-----------|-------|------------|----|-------|--:|--:|--:|------:|---------:|------:|",
        ]
        for row in rows:
            lines.append(
                f"| {row['experiment']} | {row.get('group') or '-'} | {row['generation_target']} | "
                f"{row['generation_index']} | {row['judge_target']} | {row['majority_improved']} | "
                f"{row['majority_equal']} | {row['majority_regressed']} | {row['stable_queries']} | "
                f"{row['volatile_queries']} | {_format_float(row['overall_delta_mean'])} |"
            )
        output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Tuning batch summary")
    print(f"Batch: {batch.get('batch_name')}")
    print(f"Rows : {len(rows)}")
    for row in rows:
        print(
            f"{row['experiment']} / {row['generation_target']} / {row['judge_target']} "
            f"=> I={row['majority_improved']} = {row['majority_equal']} R={row['majority_regressed']} "
            f"stable={row['stable_queries']} delta={_format_float(row['overall_delta_mean'])}"
        )


if __name__ == "__main__":
    main()
