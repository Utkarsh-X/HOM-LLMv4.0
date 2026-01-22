"""LLM-based judge for HOM-LLM delta evaluation.

Compares HOM-LLM answers to the fixed Cursor baseline and emits
per-dimension ordinal scores plus natural-language explanations.

Constraints:
- Uses separate judge config (model + API key).
- No imports from homllm core.
- Read-only baseline (no regeneration).
- Append-only outputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def read_json(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path) -> List[Dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: List[Dict]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


@dataclass
class JudgeConfig:
    model: str
    api_key: str
    base_url: Optional[str] = None


def load_judge_config(path: Path) -> JudgeConfig:
    cfg = read_json(path)
    model = cfg.get("model")
    api_key = cfg.get("api_key")
    base_url = cfg.get("base_url")
    if not model or not api_key:
        raise ValueError("judge_config.json must include 'model' and 'api_key'")
    return JudgeConfig(model=model, api_key=api_key, base_url=base_url)


def build_prompt(baseline_answer: str, candidate_answer: str, query_text: str) -> List[Dict[str, str]]:
    system_msg = (
        "You are an impartial evaluator. Compare two answers to the same query.\n"
        "Focus on relative quality, not truth against ground truth. Output JSON only.\n"
        "Scores must be integers 1-5 (1=poor, 5=excellent). Lower verbosity is better; "
        "hallucination risk: 1=very risky, 5=very safe. Provide a concise rationale."
    )
    user_msg = (
        f"Query:\n{query_text}\n\n"
        "Baseline Answer:\n"
        f"{baseline_answer}\n\n"
        "Candidate Answer (HOM-LLM):\n"
        f"{candidate_answer}\n\n"
        "Return JSON with keys: scores (object with semantic_correctness, factual_consistency, completeness, "
        "clarity, relevance, hallucination_risk, verbosity, overall_quality), "
        "verdict (improved|equal|regressed), explanation (1-3 sentences), "
        "and key_differences (short bullet-style sentences)."
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def ensure_openai_client(cfg: JudgeConfig):
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "openai package is required for the judge. Install via `pip install openai`."
        ) from exc

    client_kwargs: Dict[str, Any] = {"api_key": cfg.api_key}
    if cfg.base_url:
        client_kwargs["base_url"] = cfg.base_url
    return OpenAI(**client_kwargs)


def call_judge(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Dict:
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        temperature=0,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("Judge model returned empty content.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse judge output as JSON: {content}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM judge for HOM-LLM vs Cursor baseline.")
    parser.add_argument("--responses", type=Path, required=True, help="Path to responses JSONL from run_experiment")
    parser.add_argument("--baseline", type=Path, required=True, help="Path to cursor_baseline.json")
    parser.add_argument("--judge-config", type=Path, required=True, help="Path to judge_config.json")
    parser.add_argument("--output", type=Path, help="Optional output path for judge_results.jsonl")
    args = parser.parse_args()

    responses = read_jsonl(args.responses)
    baseline_payload = read_json(args.baseline)
    baseline_map = {item["query_id"]: item for item in baseline_payload.get("queries", [])}

    cfg = load_judge_config(args.judge_config)
    client = ensure_openai_client(cfg)

    output_path = args.output or args.responses.parent / "judge_results.jsonl"

    records: List[Dict] = []
    for resp in responses:
        qid = resp.get("query_id")
        base = baseline_map.get(qid)
        if not base:
            sys.stderr.write(f"[WARN] Missing baseline for query_id {qid}, skipping.\n")
            continue
        messages = build_prompt(
            baseline_answer=base.get("answer", ""),
            candidate_answer=resp.get("answer_text", ""),
            query_text=resp.get("query_text", ""),
        )
        try:
            judged = call_judge(client, cfg, messages)
        except Exception as exc:  # pragma: no cover - runtime guard
            sys.stderr.write(f"[ERROR] Judge failed for query {qid}: {exc}\n")
            continue

        record = {
            "query_id": qid,
            "query_text": resp.get("query_text"),
            "candidate_model": resp.get("model_name"),
            "candidate_provider": resp.get("provider"),
            "baseline_system": baseline_payload.get("metadata", {}).get("system", "Cursor"),
            "judge_model": cfg.model,
            "scores": judged.get("scores", {}),
            "verdict": judged.get("verdict"),
            "explanation": judged.get("explanation"),
            "key_differences": judged.get("key_differences"),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records.append(record)
        write_jsonl(output_path, [record])

    print(f"Saved judge results to: {output_path}")


if __name__ == "__main__":
    main()
