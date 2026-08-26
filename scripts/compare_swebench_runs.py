"""Compare SWE-bench Lite benchmark runs side by side.

Inputs are one or more of:
- a run artifact directory containing ``evaluation/summary.json``
  (``<artifact_root>/<run_id>/``);
- a direct path to an ``evaluation/summary.json`` file;
- a saved stdout blob from ``eval-swebench-lite`` (the JSON object with
  ``run_id`` / ``case_results`` / ``summary_metrics`` keys).

The comparison is read-only and deterministic:

1. Headline pass rates per run.
2. Case x run matrix showing pass/fail plus each failure's error code.
3. Flips between the first run and each later run (fixed / regressed).
4. Error-code histograms per run.
5. Token + agent-turn budgets per run (averages over cases reporting them).

Usage:
    python scripts/compare_swebench_runs.py <run_a> [<run_b> ...] [--format table|json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CASE_FIELDS = (
    "passed",
    "error_code",
    "actual_stop_reason",
)

METRIC_FIELDS = (
    "provider_tokens_in",
    "provider_tokens_out",
    "agent_turn_count",
    "agent_tool_calls",
)


def _load_summary(path: Path) -> dict:
    if path.is_dir():
        candidate = path / "evaluation" / "summary.json"
        if candidate.exists():
            path = candidate
        else:
            raise SystemExit(f"no evaluation/summary.json under {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "case_results" not in payload:
        raise SystemExit(f"{path} does not look like a benchmark summary")
    return payload


def _normalize(payload: dict) -> dict:
    cases: dict[str, dict] = {}
    for row in payload.get("case_results", []):
        metrics = row.get("metrics") or {}
        entry = {field: row.get(field) for field in CASE_FIELDS}
        for field in METRIC_FIELDS:
            value = metrics.get(field)
            entry[field] = float(value) if isinstance(value, (int, float)) else None
        quality = metrics.get("benchmark_quality_gate")
        entry["quality_gate"] = quality
        entry["agent_stop_reason"] = metrics.get("agent_stop_reason")
        cases[str(row.get("case_id"))] = entry

    all_tokens_in = [c[METRIC_FIELDS[0]] for c in cases.values() if c[METRIC_FIELDS[0]] is not None]
    all_tokens_out = [c[METRIC_FIELDS[1]] for c in cases.values() if c[METRIC_FIELDS[1]] is not None]
    turns = [c["agent_turn_count"] for c in cases.values() if c["agent_turn_count"] is not None]

    return {
        "run_id": str(payload.get("run_id") or "(unnamed)"),
        "total": int(payload.get("total_cases") or len(cases)),
        "passed": int(payload.get("passed_cases") or sum(1 for c in cases.values() if c["passed"])),
        "failed": int(payload.get("failed_cases") or sum(1 for c in cases.values() if not c["passed"])),
        "cases": cases,
        "error_code_counts": (payload.get("summary_metrics") or {}).get("error_code_counts") or {},
        "avg_tokens_in": (sum(all_tokens_in) / len(all_tokens_in)) if all_tokens_in else None,
        "avg_tokens_out": (sum(all_tokens_out) / len(all_tokens_out)) if all_tokens_out else None,
        "avg_agent_turns": (sum(turns) / len(turns)) if turns else None,
    }


def _mark(runs: list[dict], case_id: str, index: int) -> str:
    entry = runs[index]["cases"].get(case_id)
    if entry is None:
        return "-"
    if entry["passed"]:
        return "pass"
    code = entry.get("error_code") or entry.get("actual_stop_reason") or "fail"
    return f"FAIL({code})"


def _print_table(runs: list[dict]) -> None:
    print("== headline ==")
    for run in runs:
        rate = (100.0 * run["passed"] / run["total"]) if run["total"] else 0.0
        parts = [
            f"{run['run_id']}: {run['passed']}/{run['total']} passed ({rate:.0f}%)"
        ]
        if run["avg_tokens_in"] is not None:
            parts.append(
                f"tokens/case ~{run['avg_tokens_in']:.0f}in/{(run['avg_tokens_out'] or 0):.0f}out"
            )
        if run["avg_agent_turns"] is not None:
            parts.append(f"agent turns ~{run['avg_agent_turns']:.1f}")
        print("  " + " | ".join(parts))

    all_cases = sorted({cid for run in runs for cid in run["cases"]})
    header = f"{'case':<40}" + "".join(f"| {run['run_id'][:28]:<30}" for run in runs)
    print("\n== case x run ==")
    print(header)
    for case_id in all_cases:
        row = f"{case_id[:39]:<40}"
        for index in range(len(runs)):
            row += f"| {_mark(runs, case_id, index):<30}"
        print(row)

    first = runs[0]
    print("\n== flips vs first run ==")
    for later in runs[1:]:
        shared = set(first["cases"]) & set(later["cases"])
        fixed = sorted(c for c in shared if not first["cases"][c]["passed"] and later["cases"][c]["passed"])
        regressed = sorted(c for c in shared if first["cases"][c]["passed"] and not later["cases"][c]["passed"])
        print(
            f"  {first['run_id']} -> {later['run_id']}: "
            f"fixed={len(fixed)} regressed={len(regressed)}"
        )
        for name, group in (("fixed", fixed), ("regressed", regressed)):
            for case_id in group:
                print(f"    {name}: {case_id}")

    print("\n== error codes ==")
    for run in runs:
        codes = dict(sorted(run["error_code_counts"].items()))
        print(f"  {run['run_id']}: {json.dumps(codes, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="run dirs, summary.json files, or stdout blobs")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--out", type=Path, help="also write the JSON comparison here")
    args = parser.parse_args(argv)

    runs = [_normalize(_load_summary(path)) for path in args.runs]

    comparison = {
        "runs": [
            {
                key: run[key]
                for key in (
                    "run_id",
                    "total",
                    "passed",
                    "failed",
                    "error_code_counts",
                    "avg_tokens_in",
                    "avg_tokens_out",
                    "avg_agent_turns",
                )
            }
            for run in runs
        ],
        "cases": {
            case_id: [_mark(runs, case_id, index) for index in range(len(runs))]
            for case_id in sorted({cid for run in runs for cid in run["cases"]})
        },
    }

    if args.out is not None:
        args.out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
        print(f"comparison written: {args.out}")

    if args.format == "json":
        print(json.dumps(comparison, indent=2))
    else:
        _print_table(runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
