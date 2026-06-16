"""Run-to-run delta comparison for HOM-LLM evaluations.

Loads judge outputs from two runs and reports directional deltas, answer-shape
changes, and selected telemetry differences.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


CSV_FIELDS = [
    "query_id",
    "a_overall",
    "b_overall",
    "delta",
    "verdict_a",
    "verdict_b",
    "answer_chars_a",
    "answer_chars_b",
    "answer_chars_delta",
    "tokens_out_a",
    "tokens_out_b",
    "tokens_out_delta",
    "bm25_count_a",
    "bm25_count_b",
    "vector_count_a",
    "vector_count_b",
    "context_blocks_a",
    "context_blocks_b",
    "retrieval_disagreement_a",
    "retrieval_disagreement_b",
    "top_file_concentration_a",
    "top_file_concentration_b",
]


def read_jsonl(path: Path) -> List[Dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_scores(path: Path) -> Dict[int, Dict]:
    records = read_jsonl(path)
    return {int(r["query_id"]): r for r in records}


def _find_judge_file(run_dir: Path) -> Path:
    direct = run_dir / "judge_results.jsonl"
    if direct.exists():
        return direct
    candidates = sorted(run_dir.glob("judge_results__*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No judge_results*.jsonl found in {run_dir}")
    return candidates[0]


def _load_responses(run_dir: Path) -> Dict[int, Dict]:
    path = run_dir / "responses.jsonl"
    if not path.exists():
        return {}
    return load_scores(path)


def _score_value(record: Dict, metric: str, side: str = "candidate") -> float:
    value = (record.get("scores") or {}).get(metric, 0)
    if isinstance(value, dict):
        value = value.get(side, 0)
    return float(value or 0)


def _read_telemetry(response: Dict | None) -> Dict[str, Any]:
    if not response:
        return {}
    telemetry_path = response.get("telemetry_path")
    if not telemetry_path:
        return {}
    path = Path(telemetry_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _phase(telemetry: Dict[str, Any], name: str) -> Dict[str, Any]:
    return (telemetry.get("phases") or {}).get(name, {}) or {}


def _telemetry_summary(response: Dict | None) -> Dict[str, Any]:
    telemetry = _read_telemetry(response)
    retrieval = _phase(telemetry, "RETRIEVAL")
    context = _phase(telemetry, "CONTEXT")
    synthesis = context.get("context_synthesis") or {}
    depth = context.get("depth_preservation_check") or {}
    return {
        "answer_chars": len(response.get("answer_text") or "") if response else None,
        "tokens_out": response.get("tokens_out") if response else None,
        "bm25_count": retrieval.get("bm25_count"),
        "vector_count": retrieval.get("vector_count"),
        "context_blocks": context.get("blocks"),
        "retrieval_disagreement": synthesis.get("retrieval_disagreement"),
        "top_file_concentration": depth.get("top_file_concentration_ratio"),
    }


def delta(a: float, b: float) -> float:
    return b - a


def summarize(
    a_scores: Dict[int, Dict],
    b_scores: Dict[int, Dict],
    a_responses: Dict[int, Dict] | None = None,
    b_responses: Dict[int, Dict] | None = None,
) -> Tuple[List[Dict], float]:
    rows = []
    deltas = []
    a_responses = a_responses or {}
    b_responses = b_responses or {}
    for qid in sorted(a_scores):
        a_rec = a_scores[qid]
        b_rec = b_scores.get(qid)
        if not b_rec:
            continue
        a_overall = _score_value(a_rec, "overall_quality")
        b_overall = _score_value(b_rec, "overall_quality")
        d = delta(a_overall, b_overall)
        deltas.append(d)
        a_telemetry = _telemetry_summary(a_responses.get(qid))
        b_telemetry = _telemetry_summary(b_responses.get(qid))
        answer_chars_delta = None
        if a_telemetry["answer_chars"] is not None and b_telemetry["answer_chars"] is not None:
            answer_chars_delta = b_telemetry["answer_chars"] - a_telemetry["answer_chars"]
        tokens_out_delta = None
        if a_telemetry["tokens_out"] is not None and b_telemetry["tokens_out"] is not None:
            tokens_out_delta = b_telemetry["tokens_out"] - a_telemetry["tokens_out"]
        rows.append(
            {
                "query_id": qid,
                "a_overall": a_overall,
                "b_overall": b_overall,
                "delta": d,
                "verdict_a": a_rec.get("verdict"),
                "verdict_b": b_rec.get("verdict"),
                "answer_chars_a": a_telemetry["answer_chars"],
                "answer_chars_b": b_telemetry["answer_chars"],
                "answer_chars_delta": answer_chars_delta,
                "tokens_out_a": a_telemetry["tokens_out"],
                "tokens_out_b": b_telemetry["tokens_out"],
                "tokens_out_delta": tokens_out_delta,
                "bm25_count_a": a_telemetry["bm25_count"],
                "bm25_count_b": b_telemetry["bm25_count"],
                "vector_count_a": a_telemetry["vector_count"],
                "vector_count_b": b_telemetry["vector_count"],
                "context_blocks_a": a_telemetry["context_blocks"],
                "context_blocks_b": b_telemetry["context_blocks"],
                "retrieval_disagreement_a": a_telemetry["retrieval_disagreement"],
                "retrieval_disagreement_b": b_telemetry["retrieval_disagreement"],
                "top_file_concentration_a": a_telemetry["top_file_concentration"],
                "top_file_concentration_b": b_telemetry["top_file_concentration"],
            }
        )
    aggregate = sum(deltas) / len(deltas) if deltas else 0.0
    return rows, aggregate


def summarize_run_dirs(run_a_dir: Path, run_b_dir: Path) -> Tuple[List[Dict], float]:
    a_scores = load_scores(_find_judge_file(run_a_dir))
    b_scores = load_scores(_find_judge_file(run_b_dir))
    return summarize(a_scores, b_scores, _load_responses(run_a_dir), _load_responses(run_b_dir))


def write_csv(rows: List[Dict], path: Path) -> None:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: Any) -> str:
    return "-" if value is None else str(value)


def write_markdown(rows: List[Dict], aggregate: float, path: Path, run_a: str, run_b: str) -> None:
    lines = [
        f"# Delta Report: {run_a} -> {run_b}",
        "",
        f"- Average overall delta: {aggregate:+.2f}",
        "",
        "| Query | Overall A | Overall B | Delta | Verdict A | Verdict B | Vector A | Vector B | Blocks A | Blocks B | Answer Delta |",
        "|-------|-----------|-----------|-------|-----------|-----------|---------:|---------:|---------:|---------:|-------------:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['query_id']:02d} | {row['a_overall']:.2f} | {row['b_overall']:.2f} | "
            f"{row['delta']:+.2f} | {row.get('verdict_a','')} | {row.get('verdict_b','')} | "
            f"{_fmt(row.get('vector_count_a'))} | {_fmt(row.get('vector_count_b'))} | "
            f"{_fmt(row.get('context_blocks_a'))} | {_fmt(row.get('context_blocks_b'))} | "
            f"{_fmt(row.get('answer_chars_delta'))} |"
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

    rows, aggregate = summarize_run_dirs(run_a_dir, run_b_dir)

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
