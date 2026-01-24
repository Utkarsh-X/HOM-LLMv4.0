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
    provider: str = "openai"  # "openai" or "gemini"
    base_url: Optional[str] = None


def load_judge_config(path: Path) -> JudgeConfig:
    cfg = read_json(path)
    model = cfg.get("model")
    api_key = cfg.get("api_key")
    provider = cfg.get("provider", "openai")  # Default to openai for backward compat
    base_url = cfg.get("base_url")
    if not model or not api_key:
        raise ValueError("judge_config.json must include 'model' and 'api_key'")
    return JudgeConfig(model=model, api_key=api_key, provider=provider, base_url=base_url)


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


def ensure_gemini_client(cfg: JudgeConfig):
    """Create Gemini client for judge."""
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai package is required for Gemini judge. Install via `pip install google-genai`."
        ) from exc
    
    return genai.Client(api_key=cfg.api_key)


def call_judge_openai(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Dict:
    """Call OpenAI-compatible API for judging."""
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        temperature=0,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("Judge model returned empty content.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse judge output as JSON: {content}") from exc


def call_judge_gemini(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Dict:
    """Call Gemini API for judging."""
    # Convert messages to Gemini format
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
    
    prompt = f"{system_msg}\n\n{user_msg}" if system_msg else user_msg
    
    response = client.models.generate_content(
        model=cfg.model,
        contents=prompt,
        config={
            "temperature": 0,
            "max_output_tokens": 4000,  # Increased for full response
        },
    )
    
    content = response.text if response.text else ""
    if not content:
        raise RuntimeError("Gemini judge returned empty content.")
    
    # Try to extract JSON from response (may have markdown wrapper)
    import re
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        content = json_match.group(0)
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        # Return partial result if JSON is truncated
        sys.stderr.write(f"[WARN] Partial JSON response, returning raw content\n")
        return {
            "scores": {},
            "verdict": "error",
            "explanation": f"JSON parse failed: {content[:200]}...",
            "key_differences": [],
        }


def call_judge(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Dict:
    """Call judge API (OpenAI or Gemini)."""
    if cfg.provider == "gemini":
        return call_judge_gemini(client, cfg, messages)
    else:
        return call_judge_openai(client, cfg, messages)


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
    
    # Create appropriate client based on provider
    if cfg.provider == "gemini":
        client = ensure_gemini_client(cfg)
    else:
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
        
        # Print result to terminal
        verdict = judged.get("verdict", "unknown")
        scores = judged.get("scores", {})
        verdict_icon = "✔" if verdict == "improved" else "≈" if verdict == "equal" else "✗"
        print(f"\n{'='*70}")
        print(f"Query {qid}: {verdict_icon} {verdict.upper()}")
        print(f"-"*70)
        print(f"Scores:")
        for key, val in scores.items():
            print(f"  {key:25s}: {val}")
        print(f"\nExplanation: {judged.get('explanation', 'N/A')}")
        if judged.get("key_differences"):
            print(f"Key Differences:")
            for diff in judged.get("key_differences", []):
                print(f"  • {diff}")

    # Print summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    verdicts = [r.get("verdict", "unknown") for r in records]
    improved = verdicts.count("improved")
    equal = verdicts.count("equal")
    regressed = verdicts.count("regressed")
    
    print(f"Total queries judged: {len(records)}")
    print(f"  ✔ Improved:  {improved}")
    print(f"  ≈ Equal:     {equal}")
    print(f"  ✗ Regressed: {regressed}")
    
    # Average scores
    if records:
        all_scores = [r.get("scores", {}) for r in records]
        score_keys = set()
        for s in all_scores:
            score_keys.update(s.keys())
        
        if score_keys:
            print(f"\nAverage Scores:")
            for key in sorted(score_keys):
                vals = []
                for s in all_scores:
                    if key in s:
                        v = s[key]
                        # Handle nested dict format: {'baseline': X, 'candidate': Y}
                        if isinstance(v, dict) and 'candidate' in v:
                            vals.append(v['candidate'])
                        elif isinstance(v, (int, float)):
                            vals.append(v)
                if vals:
                    avg = sum(vals) / len(vals)
                    print(f"  {key:25s}: {avg:.2f}")
    
    print(f"\nSaved judge results to: {output_path}")


if __name__ == "__main__":
    main()
