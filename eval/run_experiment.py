"""Delta evaluation experiment runner for HOM-LLM v2.0.

Runs selected canonical queries through the existing runtime CLI (read-only)
and stores raw responses plus telemetry for downstream judging and comparison.

Key guarantees:
- Does not import or modify core homllm modules.
- Uses subprocess to call `runtime/run_query.py`.
- Append-only response storage (JSONL).
- Supports flexible query selection (`--select`).
- Optional terminal telemetry summary (read-only).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_CLI = ROOT / "runtime" / "run_query.py"
QUERIES_PATH = ROOT / "eval" / "queries.json"
BASE_OUTPUT_DIR = ROOT / "eval" / "runs"


class SelectionError(ValueError):
    pass


def parse_selection(expr: str, total: int) -> List[int]:
    """Parse selection expressions like '3', '1,5,7', '1-10', 'all'."""
    expr = expr.strip().lower()
    if expr == "all":
        return list(range(1, total + 1))

    parts = expr.split(",")
    selected: List[int] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            if not start_str.isdigit() or not end_str.isdigit():
                raise SelectionError(f"Invalid range: {part}")
            start, end = int(start_str), int(end_str)
            if start < 1 or end > total or start > end:
                raise SelectionError(f"Range out of bounds: {part}")
            selected.extend(range(start, end + 1))
        else:
            if not part.isdigit():
                raise SelectionError(f"Invalid query id: {part}")
            value = int(part)
            if value < 1 or value > total:
                raise SelectionError(f"Query id out of bounds: {value}")
            selected.append(value)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for v in selected:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


@dataclass
class QueryRecord:
    query_id: int
    query_text: str


def load_queries() -> List[QueryRecord]:
    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    queries = payload.get("queries", [])
    return [QueryRecord(q["query_id"], q["query_text"]) for q in queries]


def extract_result_text(output_lines: List[str]) -> str:
    """Parse rendered answer between 'ANSWER' header and the closing === line.
    
    Output format from run_query.py print_answer_box:
    ================================================================================
    ANSWER
    --------------------------------------------------------------------------------
    <answer content>
    ================================================================================
    """
    # Find the ANSWER section
    in_answer = False
    answer_start = None
    
    for idx, line in enumerate(output_lines):
        if "ANSWER" in line and idx > 0 and "===" in output_lines[idx - 1]:
            in_answer = True
            answer_start = idx + 1  # Skip the "---" separator
            continue
        if in_answer and "===" in line:
            # Found the closing marker
            answer_lines = output_lines[answer_start + 1:idx]  # Skip separator line
            return "\n".join(line.rstrip() for line in answer_lines).strip()
    
    # Fallback: try legacy "RESULT:" format
    for idx, line in enumerate(output_lines):
        if "RESULT:" in line:
            collected = []
            for line2 in output_lines[idx + 1:]:
                if "====" in line2:
                    break
                collected.append(line2.rstrip())
            return "\n".join(collected).strip()
    
    return ""


def extract_telemetry_path(stdout_text: str) -> Optional[Path]:
    match = re.search(r"artifacts[/\\\\]runs[/\\\\]([^/\\\\]+)[/\\\\]telemetry\.json", stdout_text)
    if not match:
        return None
    rel_path = Path("artifacts") / "runs" / match.group(1) / "telemetry.json"
    return (ROOT / rel_path).resolve()


def extract_run_id_from_path(path: Optional[Path]) -> Optional[str]:
    if not path:
        return None
    try:
        # artifacts/runs/<run_id>/telemetry.json
        return path.parent.name
    except Exception:
        return None


def load_telemetry(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def format_ms(value: float) -> int:
    return int(round(value))


def print_telemetry_summary(query_id: int, query_text: str, telemetry: Dict, run_id: Optional[str]) -> None:
    phases: Dict[str, Dict] = telemetry.get("phases", {})

    def phase_ms(name: str) -> int:
        phase = phases.get(name, {})
        return format_ms(phase.get("duration_ms", 0.0))

    gen_meta = phases.get("GENERATION", {})
    provider = gen_meta.get("provider", "unknown")
    model = gen_meta.get("model", "unknown")
    tokens_in = gen_meta.get("tokens_in", 0)
    tokens_out = gen_meta.get("tokens_out", 0)
    status = gen_meta.get("status", "UNKNOWN")

    total_latency = sum(phase_ms(p) for p in ("RETRIEVAL", "RANKING", "CONTEXT", "GENERATION"))

    retrieval = phases.get("RETRIEVAL", {})
    ranking = phases.get("RANKING", {})
    context = phases.get("CONTEXT", {})

    print(f"[QUERY {query_id:02d} COMPLETED]")
    if run_id:
        print(f"Run ID      : {run_id}")
    print(f"Query       : {query_text[:80]}")
    print()
    print(
        f"RETRIEVAL   : {phase_ms('RETRIEVAL')} ms | "
        f"candidates={retrieval.get('candidates', 0)} "
        f"(bm25={retrieval.get('bm25_count', 0)}, vector={retrieval.get('vector_count', 0)})"
    )
    print(
        f"RANKING     : {phase_ms('RANKING')} ms | reranker={bool(ranking.get('reranker'))}"
    )
    print(
        f"CONTEXT     : {phase_ms('CONTEXT')} ms | "
        f"blocks={context.get('blocks', 0)} tokens={context.get('tokens', 0)}/{context.get('token_budget', 0)}"
    )
    print(
        f"GENERATION  : {phase_ms('GENERATION')} ms | "
        f"model={model} | in={tokens_in} out={tokens_out} | status={status}"
    )
    print("-" * 50)


def run_single_query(
    query: QueryRecord,
    args: argparse.Namespace,
) -> Dict:
    cmd = [
        sys.executable,
        str(RUNTIME_CLI),
        "--query",
        query.query_text,
        "--config",
        str(args.config),
        "--json",
    ]
    if args.provider:
        cmd.extend(["--provider", args.provider])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.intent:
        cmd.extend(["--intent", args.intent])
    if args.raw:
        cmd.append("--raw")
    if args.no_file_mapping:
        cmd.append("--no-file-mapping")
    if args.intelligence_levels:
        cmd.extend(["--intelligence-levels", args.intelligence_levels])
    if args.token_attribution:
        cmd.append("--token-attribution")
    if args.reasoning_contracts:
        cmd.append("--reasoning-contracts")
    if args.assertion_readability:
        cmd.append("--assertion-readability")
    if args.reasoning_diagnostics:
        cmd.append("--reasoning-diagnostics")

    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    combined_output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    combined_lines = combined_output.splitlines()

    telemetry_path = extract_telemetry_path(combined_output)
    telemetry = load_telemetry(telemetry_path) if telemetry_path and telemetry_path.exists() else {}
    run_id = extract_run_id_from_path(telemetry_path)
    answer_text = extract_result_text(combined_lines)

    phases = telemetry.get("phases", {})
    gen_meta = phases.get("GENERATION", {})

    response = {
        "query_id": query.query_id,
        "query_text": query.query_text,
        "system": "HOM-LLM",
        "model_name": gen_meta.get("model") or args.model or "unknown",
        "provider": gen_meta.get("provider") or args.provider or "unknown",
        "answer_text": answer_text,
        "tokens_in": gen_meta.get("tokens_in"),
        "tokens_out": gen_meta.get("tokens_out"),
        "latency_ms": sum(phase.get("duration_ms", 0.0) for phase in phases.values()),
        "status": gen_meta.get("status", "UNKNOWN"),
        "telemetry_path": str(telemetry_path) if telemetry_path else None,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "answer_text": answer_text,
    }

    if args.telemetry_print and telemetry:
        print_telemetry_summary(query.query_id, query.query_text, telemetry, run_id)

    if completed.returncode != 0:
        sys.stderr.write(f"[WARN] Query {query.query_id} exited with {completed.returncode}\n")
        sys.stderr.write(completed.stderr)

    return response


def persist_answer_txt(response: Dict, answer_text: str, run_dir: Path) -> None:
    """Persist answer text to run_dir/generated_answers/query_XX.txt"""
    answers_dir = run_dir / "generated_answers"
    ensure_dir(answers_dir)
    query_id = response.get("query_id")
    model = response.get("model_name", "unknown")
    provider = response.get("provider", "unknown")
    status = response.get("status", "UNKNOWN")
    run_id = response.get("run_id") or "unknown"
    file_path = answers_dir / f"query_{int(query_id):02d}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"QUERY_ID   : {int(query_id):02d}\n")
        f.write(f"RUN_ID     : {run_id}\n")
        f.write(f"MODEL      : {model}\n")
        f.write(f"PROVIDER   : {provider}\n")
        f.write(f"STATUS     : {status}\n")
        f.write("--- ANSWER ---\n")
        f.write(answer_text or "")


def write_jsonl(path: Path, records: Iterable[Dict]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_run_info(path: Path, args: argparse.Namespace, selected: List[int]) -> None:
    info = {
        "run_name": path.name,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config": str(args.config),
        "provider": args.provider,
        "model": args.model,
        "intent": args.intent,
        "selection": selected,
    }
    with open(path / "run_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HOM-LLM evaluation queries (delta-friendly).")
    parser.add_argument("--select", type=str, default="all", help="Query selection: all | N | 1,2,3 | 5-10")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"), help="Config for core pipeline")
    parser.add_argument("--provider", type=str, help="Generation provider")
    parser.add_argument("--model", type=str, help="Generation model")
    parser.add_argument("--intent", type=str, help="Intent to pass through")
    parser.add_argument("--raw", action="store_true", help="Pass --raw to runtime (no normalization)")
    parser.add_argument("--no-file-mapping", action="store_true", help="Disable file-id to path mapping in runtime")
    parser.add_argument("--run-name", type=str, help="Optional run name (default: run_YYYYMMDD_HHMMSS)")
    parser.add_argument("--output-dir", type=Path, default=BASE_OUTPUT_DIR, help="Base directory for run outputs")
    parser.add_argument(
        "--telemetry-print",
        action="store_true",
        default=True,
        help="Print per-query telemetry summary (read-only)",
    )
    parser.add_argument(
        "--intelligence-levels", type=str, default=None,
        help="Override intelligence levels: none|l1|l1,l2|l1,l2,l3"
    )
    parser.add_argument(
        "--token-attribution", action="store_true",
        help="Enable token attribution telemetry"
    )
    parser.add_argument(
        "--reasoning-contracts", action="store_true",
        help="Enable Phase-3A/3B reasoning contract enforcement"
    )
    parser.add_argument(
        "--assertion-readability", action="store_true",
        help="Enable assertion readability analysis"
    )
    parser.add_argument(
        "--reasoning-diagnostics", action="store_true",
        help="Enable reasoning diagnostics telemetry"
    )

    args = parser.parse_args()

    queries = load_queries()
    try:
        selected_ids = parse_selection(args.select, total=len(queries))
    except SelectionError as e:
        sys.stderr.write(f"Selection error: {e}\n")
        sys.exit(1)

    selected_queries = [q for q in queries if q.query_id in selected_ids]
    if not selected_queries:
        sys.stderr.write("No queries selected.\n")
        sys.exit(1)

    run_name = args.run_name or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = args.output_dir / run_name
    ensure_dir(run_dir)

    write_run_info(run_dir, args, selected_ids)

    responses_path = run_dir / "responses.jsonl"

    total = len(selected_queries)
    for idx, query in enumerate(selected_queries, start=1):
        response = run_single_query(query, args)
        write_jsonl(responses_path, [response])
        persist_answer_txt(response, response.get("answer_text", ""), run_dir)

        status_icon = "✔" if response.get("status", "").upper() == "OK" else "⚠"
        print(f"[RUN {idx}/{total}] Query {query.query_id:02d} {status_icon} {response.get('status', 'DONE')}")

    print(f"Saved responses to: {responses_path}")


if __name__ == "__main__":
    main()
