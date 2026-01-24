"""
Intelligence comparison experiment runner.

Runs the same queries with different intelligence level configurations
to enable empirical comparison of Level-1, Level-2, and Level-3 effects.

For each query, runs 4 passes:
1. No intelligence (none)
2. Level-1 only (l1)
3. Level-1 + Level-2 (l1,l2)
4. Full intelligence (l1,l2,l3)

Captures:
- query
- intelligence_levels
- context_tokens_before
- context_tokens_after
- visible_prompt_tokens (if --token-attribution)
- tokens_in
- tokens_out
- generation_status
- response_text

Results stored in: artifacts/intelligence_comparison/<run_id>.json

Key guarantees:
- Does not import or modify core homllm modules
- Uses subprocess to call runtime/run_query.py
- No scoring or ranking of outputs (human-led evaluation)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_CLI = ROOT / "runtime" / "run_query.py"
QUERIES_PATH = ROOT / "eval" / "queries.json"
OUTPUT_BASE_DIR = ROOT / "artifacts" / "intelligence_comparison"


# Intelligence level configurations to compare
INTELLIGENCE_LEVELS = [
    ("none", "none"),
    ("l1", "l1"),
    ("l1_l2", "l1,l2"),
    ("l1_l2_l3", "l1,l2,l3"),
]


@dataclass
class RunResult:
    """Result from a single query run with specific intelligence level."""
    query: str
    intelligence_levels: str
    context_tokens_before: Optional[int]
    context_tokens_after: Optional[int]
    visible_prompt_tokens: Optional[int]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    generation_status: str
    response_text: str
    run_id: Optional[str] = None
    telemetry: Optional[Dict] = None


def load_queries() -> List[Dict]:
    """Load queries from the eval queries file."""
    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("queries", [])


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
            start, end = int(start_str), int(end_str)
            if start < 1 or end > total or start > end:
                raise ValueError(f"Range out of bounds: {part}")
            selected.extend(range(start, end + 1))
        else:
            value = int(part)
            if value < 1 or value > total:
                raise ValueError(f"Query id out of bounds: {value}")
            selected.append(value)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for v in selected:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def extract_telemetry_path(stdout_text: str) -> Optional[Path]:
    """Extract telemetry.json path from CLI output."""
    match = re.search(r"artifacts[/\\]+runs[/\\]+([^/\\]+)[/\\]+telemetry\.json", stdout_text)
    if not match:
        return None
    rel_path = Path("artifacts") / "runs" / match.group(1) / "telemetry.json"
    return (ROOT / rel_path).resolve()


def load_telemetry(path: Path) -> Dict:
    """Load telemetry JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_answer_text(output: str) -> str:
    """Extract answer from CLI output between === markers."""
    lines = output.splitlines()
    in_answer = False
    answer_lines = []
    
    for line in lines:
        if "ANSWER" in line and "===" in lines[max(0, lines.index(line) - 1):lines.index(line) + 1][0] if lines else False:
            in_answer = True
            continue
        if in_answer:
            if "===" in line:
                break
            answer_lines.append(line)
    
    # Fallback: try to find content between === markers
    if not answer_lines:
        markers = [i for i, line in enumerate(lines) if "===" in line]
        if len(markers) >= 2:
            answer_lines = lines[markers[0] + 2:markers[1]]
    
    return "\n".join(answer_lines).strip()


def run_single_query(
    query: str,
    intelligence_level_spec: str,
    args: argparse.Namespace,
) -> RunResult:
    """Run a single query with the specified intelligence level."""
    cmd = [
        sys.executable,
        str(RUNTIME_CLI),
        "--query", query,
        "--config", str(args.config),
        "--json",
        "--intelligence-levels", intelligence_level_spec,
    ]
    
    if args.provider:
        cmd.extend(["--provider", args.provider])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.token_attribution:
        cmd.append("--token-attribution")
    
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    
    combined_output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    
    # Extract telemetry
    telemetry_path = extract_telemetry_path(combined_output)
    telemetry = load_telemetry(telemetry_path) if telemetry_path and telemetry_path.exists() else {}
    run_id = telemetry_path.parent.name if telemetry_path else None
    
    # Extract metrics from telemetry
    phases = telemetry.get("phases", {})
    context_phase = phases.get("CONTEXT", {})
    intelligence_phase = phases.get("INTELLIGENCE", {})
    generation_phase = phases.get("GENERATION", {})
    
    # Get token attribution if available
    visible_prompt_tokens = None
    # Parse from output if --token-attribution was used
    if args.token_attribution:
        match = re.search(r"visible_prompt_tokens=(\d+)", combined_output)
        if match:
            visible_prompt_tokens = int(match.group(1))
    
    # Extract answer text
    answer_text = extract_answer_text(combined_output)
    
    return RunResult(
        query=query,
        intelligence_levels=intelligence_level_spec,
        context_tokens_before=intelligence_phase.get("context_tokens_before"),
        context_tokens_after=intelligence_phase.get("context_tokens_after") or context_phase.get("tokens"),
        visible_prompt_tokens=visible_prompt_tokens,
        tokens_in=generation_phase.get("tokens_in"),
        tokens_out=generation_phase.get("tokens_out"),
        generation_status=generation_phase.get("status", "UNKNOWN"),
        response_text=answer_text,
        run_id=run_id,
        telemetry=telemetry,
    )


def run_comparison(
    queries: List[Dict],
    args: argparse.Namespace,
) -> Dict:
    """Run comparison across all intelligence levels for selected queries."""
    run_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    results = {
        "run_id": run_id,
        "timestamp": timestamp,
        "config": str(args.config),
        "provider": args.provider,
        "model": args.model,
        "token_attribution_enabled": args.token_attribution,
        "queries": [],
    }
    
    total_queries = len(queries)
    total_runs = total_queries * len(INTELLIGENCE_LEVELS)
    current_run = 0
    
    for query_data in queries:
        query_id = query_data.get("query_id")
        query_text = query_data.get("query_text")
        
        query_results = {
            "query_id": query_id,
            "query_text": query_text,
            "runs": [],
        }
        
        for level_name, level_spec in INTELLIGENCE_LEVELS:
            current_run += 1
            print(f"[{current_run}/{total_runs}] Query {query_id} with {level_name}...", end=" ", flush=True)
            
            try:
                result = run_single_query(query_text, level_spec, args)
                query_results["runs"].append({
                    "level_name": level_name,
                    "level_spec": level_spec,
                    "context_tokens_before": result.context_tokens_before,
                    "context_tokens_after": result.context_tokens_after,
                    "visible_prompt_tokens": result.visible_prompt_tokens,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "generation_status": result.generation_status,
                    "response_text": result.response_text,
                    "telemetry_run_id": result.run_id,
                })
                status = result.generation_status
                print(f"✔ {status}")
            except Exception as e:
                print(f"✗ Error: {e}")
                query_results["runs"].append({
                    "level_name": level_name,
                    "level_spec": level_spec,
                    "error": str(e),
                })
        
        results["queries"].append(query_results)
    
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run intelligence level comparison experiments."
    )
    parser.add_argument(
        "--queries-file", type=Path, default=QUERIES_PATH,
        help="JSON file containing queries"
    )
    parser.add_argument(
        "--select", type=str, default="all",
        help="Query selection: all | N | 1,2,3 | 5-10"
    )
    parser.add_argument(
        "--config", type=Path, default=Path("configs/default.yaml"),
        help="Config file path"
    )
    parser.add_argument(
        "--provider", type=str, required=True,
        help="Generation provider (gemini, openai, local)"
    )
    parser.add_argument(
        "--model", type=str,
        help="Generation model name"
    )
    parser.add_argument(
        "--token-attribution", action="store_true",
        help="Enable token attribution telemetry"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=OUTPUT_BASE_DIR,
        help="Output directory for results"
    )
    
    args = parser.parse_args()
    
    # Load queries
    if args.queries_file.exists():
        with open(args.queries_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        queries = payload.get("queries", [])
    else:
        print(f"Error: Queries file not found: {args.queries_file}")
        sys.exit(1)
    
    # Parse selection
    try:
        selected_ids = parse_selection(args.select, total=len(queries))
    except ValueError as e:
        print(f"Selection error: {e}")
        sys.exit(1)
    
    selected_queries = [q for q in queries if q.get("query_id") in selected_ids]
    if not selected_queries:
        print("No queries selected.")
        sys.exit(1)
    
    print(f"Running intelligence comparison for {len(selected_queries)} queries...")
    print(f"Levels: {', '.join(name for name, _ in INTELLIGENCE_LEVELS)}")
    print(f"Total runs: {len(selected_queries) * len(INTELLIGENCE_LEVELS)}")
    print()
    
    # Run comparison
    results = run_comparison(selected_queries, args)
    
    # Save results
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{results['run_id']}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
