"""Generate a compact regression cluster audit for HOM-LLM eval runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PLACEHOLDER_HINT = "replace placeholder text like <run_name>"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _resolve_run_inputs(
    responses: str | None,
    run_name: str | None,
    judge_results: str | None,
) -> tuple[Path, Path | None]:
    if responses and _has_placeholder(responses):
        raise SystemExit(f"Please {PLACEHOLDER_HINT} in --responses.")
    if run_name and _has_placeholder(run_name):
        raise SystemExit(f"Please {PLACEHOLDER_HINT} in --run-name.")
    if judge_results and _has_placeholder(judge_results):
        raise SystemExit(f"Please {PLACEHOLDER_HINT} in --judge-results.")

    if responses:
        responses_path = Path(responses).resolve()
    elif run_name:
        responses_path = (Path("eval") / "runs" / run_name / "responses.jsonl").resolve()
    else:
        raise SystemExit("Provide --responses or --run-name.")

    if not responses_path.exists():
        raise SystemExit(f"Responses file not found: {responses_path}")

    judge_path: Path | None
    if judge_results:
        judge_path = Path(judge_results).resolve()
        if not judge_path.exists():
            raise SystemExit(f"Judge results file not found: {judge_path}")
    else:
        candidates = sorted(responses_path.parent.glob("judge_results__*.jsonl"))
        judge_path = candidates[0].resolve() if candidates else None

    return responses_path, judge_path


def _has_placeholder(value: str) -> bool:
    return "<" in value and ">" in value


def _selected_query_ids(value: str | None) -> set[int] | None:
    if not value:
        return None
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def _query_file_name(query_id: int) -> str:
    return f"query_{query_id:02d}.txt"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _artifacts_root_for_responses(responses_path: Path) -> Path:
    run_dir = responses_path.parent
    if run_dir.parent.name == "runs" and run_dir.parent.parent.name == "eval":
        return run_dir.parent.parent.parent / "artifacts" / "runs"
    return responses_path.parent / "artifacts" / "runs"


def _preliminary_labels(
    retrieval: dict[str, Any],
    telemetry: dict[str, Any],
    generation: dict[str, Any],
) -> list[str]:
    labels: list[str] = []
    if generation.get("hallucination_flags"):
        labels.append("GENERATION_OVERREACH")

    phases = telemetry.get("phases") or {}
    context = phases.get("CONTEXT") or {}
    token_budget = float(context.get("token_budget") or 0)
    tokens = float(context.get("tokens") or 0)
    if token_budget and tokens / token_budget >= 0.9:
        labels.append("CONTEXT_PRESSURE")

    claim = phases.get("CLAIM_COVERAGE") or {}
    coverage = claim.get("coverage_ratio")
    if isinstance(coverage, (int, float)) and coverage < 0.75:
        labels.append("LOW_CLAIM_COVERAGE")

    top_candidates = retrieval.get("candidates_top20") or []
    if len(top_candidates) < 3:
        labels.append("RETRIEVAL_SPARSE")

    return labels or ["NO_OBVIOUS_LABEL"]


def _judge_by_query(path: Path | None) -> dict[int, dict[str, Any]]:
    if path is None:
        return {}
    return {int(row["query_id"]): row for row in _read_jsonl(path)}


def _build_query_summary(
    response: dict[str, Any],
    *,
    run_dir: Path,
    artifacts_root: Path,
    judge_rows: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    query_id = int(response["query_id"])
    run_id = str(response.get("run_id") or "")
    artifacts_dir = artifacts_root / run_id
    retrieval = _load_json(artifacts_dir / "retrieval_diagnostics.json")
    telemetry = _load_json(artifacts_dir / "telemetry.json")
    generation = _load_json(artifacts_dir / "generation_diagnostics.json")
    judge = judge_rows.get(query_id, {})
    answer_path = run_dir / "generated_answers" / _query_file_name(query_id)
    answer_text = answer_path.read_text(encoding="utf-8") if answer_path.exists() else ""

    return {
        "query_id": query_id,
        "query_text": response.get("query_text", ""),
        "status": response.get("status"),
        "run_id": run_id,
        "tokens_in": response.get("tokens_in"),
        "tokens_out": response.get("tokens_out"),
        "generated_answer": answer_text,
        "judge_verdict": judge.get("verdict"),
        "judge_explanation": judge.get("explanation"),
        "judge_scores": judge.get("scores", {}),
        "preliminary_labels": _preliminary_labels(retrieval, telemetry, generation),
        "retrieval": {
            "resolved_intent": retrieval.get("resolved_intent"),
            "intent_source": retrieval.get("intent_source"),
            "intent_rule": retrieval.get("intent_rule"),
            "final_output": (retrieval.get("retrieval_stage_trace") or {}).get("final_output"),
            "top_files": [item.get("file") for item in (retrieval.get("candidates_top20") or [])[:5]],
        },
        "context": (telemetry.get("phases") or {}).get("CONTEXT", {}),
        "claim_coverage": (telemetry.get("phases") or {}).get("CLAIM_COVERAGE", {}),
        "generation": generation,
    }


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = ["# Regression Cluster Audit", ""]
    for query in summary["queries"]:
        labels = " ".join(f"`{label}`" for label in query["preliminary_labels"])
        lines.extend(
            [
                f"## Query {int(query['query_id']):02d}",
                "",
                f"Verdict: `{query.get('judge_verdict')}`",
                "",
                f"Preliminary labels: {labels}",
                "",
                "### 1. Generated Answer",
                "",
                query.get("generated_answer") or "_No generated answer artifact found._",
                "",
                "### 2. Judge Explanation",
                "",
                query.get("judge_explanation") or "_No judge explanation available._",
                "",
                "### 3. Evidence Diagnostics",
                "",
                f"- Top files: {', '.join(str(item) for item in query['retrieval'].get('top_files', []) if item) or '-'}",
                f"- Context blocks: {query.get('context', {}).get('blocks')}",
                f"- Claim coverage: {query.get('claim_coverage', {}).get('coverage_ratio')}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(
    *,
    responses_path: Path,
    judge_path: Path | None,
    query_ids: set[int] | None,
) -> tuple[Path, Path]:
    run_dir = responses_path.parent
    artifacts_root = _artifacts_root_for_responses(responses_path)
    judge_rows = _judge_by_query(judge_path)
    responses = [
        row for row in _read_jsonl(responses_path)
        if query_ids is None or int(row["query_id"]) in query_ids
    ]
    queries = tuple(
        _build_query_summary(
            row,
            run_dir=run_dir,
            artifacts_root=artifacts_root,
            judge_rows=judge_rows,
        )
        for row in responses
    )
    summary = {
        "responses_path": str(responses_path),
        "judge_results_path": str(judge_path) if judge_path else None,
        "query_count": len(queries),
        "queries": queries,
    }

    json_path = run_dir / "regression_cluster_audit.json"
    md_path = run_dir / "regression_cluster_audit.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_markdown(md_path, summary)
    return md_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate regression cluster audit artifacts.")
    parser.add_argument("--responses")
    parser.add_argument("--run-name")
    parser.add_argument("--judge-results")
    parser.add_argument("--queries")
    args = parser.parse_args(argv)

    responses_path, judge_path = _resolve_run_inputs(args.responses, args.run_name, args.judge_results)
    md_path, json_path = run_audit(
        responses_path=responses_path,
        judge_path=judge_path,
        query_ids=_selected_query_ids(args.queries),
    )
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
