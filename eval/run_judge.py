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
import re
import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ------------------------------- METRIC NAMES -------------------------------
METRIC_DISPLAY_NAMES = {
    "semantic_correctness": "Semantic Correctness",
    "factual_consistency": "Factual Consistency",
    "completeness": "Completeness",
    "clarity": "Clarity",
    "relevance": "Relevance",
    "hallucination_risk": "Hallucination Safety",
    "verbosity": "Verbosity (lower=better)",
    "overall_quality": "Overall Quality",
}

METRIC_ORDER = [
    "semantic_correctness",
    "factual_consistency",
    "completeness",
    "clarity",
    "relevance",
    "hallucination_risk",
    "verbosity",
    "overall_quality",
]


# ------------------------------- IO HELPERS -------------------------------
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


# ------------------------------- RATE LIMITER -------------------------------
class RateLimiter:
    """
    Token bucket rate limiter for controlling LLM API request rate.
    
    Thread-safe implementation with configurable requests per minute.
    
    Usage:
        limiter = RateLimiter(requests_per_minute=10)
        limiter.acquire()  # Blocks until a request slot is available
    """
    
    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests allowed per minute.
                                 Default is 60 (1 per second).
                                 Set to 0 or negative to disable limiting.
        """
        self.rpm = requests_per_minute
        self.enabled = requests_per_minute > 0
        self.interval = 60.0 / requests_per_minute if self.enabled else 0
        self.last_request_time = 0.0
        self._lock = threading.Lock()
        self._request_count = 0
    
    def acquire(self) -> float:
        """
        Acquire a request slot, blocking if necessary.
        
        Returns:
            Wait time in seconds (0 if no wait was needed)
        """
        if not self.enabled:
            return 0.0
        
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.interval:
                wait_time = self.interval - time_since_last
                time.sleep(wait_time)
                self.last_request_time = time.time()
                self._request_count += 1
                return wait_time
            else:
                self.last_request_time = current_time
                self._request_count += 1
                return 0.0
    
    @property
    def request_count(self) -> int:
        """Total requests made through this limiter."""
        return self._request_count
    
    def __repr__(self) -> str:
        status = f"{self.rpm} RPM" if self.enabled else "disabled"
        return f"RateLimiter({status}, requests={self._request_count})"


# ------------------------------- CONFIG -------------------------------
@dataclass
class JudgeConfig:
    model: str
    api_key: str
    provider: str = "openai"  # "openai" or "gemini"
    base_url: Optional[str] = None
    requests_per_minute: int = 60  # Default: 60 RPM (1 per second)


def load_judge_config(path: Path) -> JudgeConfig:
    cfg = read_json(path)
    model = cfg.get("model")
    api_key = cfg.get("api_key")
    provider = cfg.get("provider", "openai")
    base_url = cfg.get("base_url")
    requests_per_minute = cfg.get("requests_per_minute", 60)
    if not model or not api_key:
        raise ValueError("judge_config.json must include 'model' and 'api_key'")
    return JudgeConfig(
        model=model, 
        api_key=api_key, 
        provider=provider, 
        base_url=base_url,
        requests_per_minute=requests_per_minute,
    )


# ------------------------------- PROMPT -------------------------------
def build_prompt(baseline_answer: str, candidate_answer: str, query_text: str) -> List[Dict[str, str]]:
    system_msg = (
        "You are an impartial evaluator comparing two answers to the same query.\n"
        "Focus on relative quality. Output ONLY valid JSON.\n\n"
        "CRITICAL: For each metric, you MUST output PAIRED scores comparing BOTH answers.\n"
        "Scores are integers 1-5 (1=poor, 5=excellent).\n"
        "For verbosity: lower is better (1=concise, 5=verbose).\n"
        "For hallucination_risk: higher is SAFER (1=very risky, 5=very safe).\n\n"
        "Required JSON format:\n"
        "{\n"
        '  "scores": {\n'
        '    "semantic_correctness": {"baseline": X, "candidate": Y},\n'
        '    "factual_consistency": {"baseline": X, "candidate": Y},\n'
        '    "completeness": {"baseline": X, "candidate": Y},\n'
        '    "clarity": {"baseline": X, "candidate": Y},\n'
        '    "relevance": {"baseline": X, "candidate": Y},\n'
        '    "hallucination_risk": {"baseline": X, "candidate": Y},\n'
        '    "verbosity": {"baseline": X, "candidate": Y},\n'
        '    "overall_quality": {"baseline": X, "candidate": Y}\n'
        "  },\n"
        '  "verdict": "improved|equal|regressed",\n'
        '  "explanation": "1-3 sentence rationale",\n'
        '  "key_differences": ["bullet 1", "bullet 2", ...]\n'
        "}"
    )
    user_msg = (
        f"Query:\n{query_text}\n\n"
        "=== BASELINE ANSWER (Cursor) ===\n"
        f"{baseline_answer}\n\n"
        "=== CANDIDATE ANSWER (HOM-LLM) ===\n"
        f"{candidate_answer}\n\n"
        "Evaluate and return the JSON with paired scores for all 8 metrics."
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ------------------------------- API CLIENTS -------------------------------
def ensure_openai_client(cfg: JudgeConfig):
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(
            "openai package is required for the judge. Install via `pip install openai`."
        ) from exc

    client_kwargs: Dict[str, Any] = {"api_key": cfg.api_key}
    if cfg.base_url:
        client_kwargs["base_url"] = cfg.base_url
    return OpenAI(**client_kwargs)


def ensure_gemini_client(cfg: JudgeConfig):
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai package is required for Gemini judge. Install via `pip install google-genai`."
        ) from exc
    return genai.Client(api_key=cfg.api_key)


def call_judge_openai(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Dict:
    completion = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        temperature=0,
        max_tokens=1500,
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
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
    prompt = f"{system_msg}\n\n{user_msg}" if system_msg else user_msg

    response = client.models.generate_content(
        model=cfg.model,
        contents=prompt,
        config={"temperature": 0, "max_output_tokens": 4000},
    )

    content = response.text if response.text else ""
    if not content:
        raise RuntimeError("Gemini judge returned empty content.")

    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        content = json_match.group(0)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        sys.stderr.write(f"[WARN] JSON parse failed, returning error structure\n")
        return {
            "scores": {},
            "verdict": "error",
            "explanation": f"JSON parse failed: {content[:200]}...",
            "key_differences": [],
        }


def call_judge(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Dict:
    if cfg.provider == "gemini":
        return call_judge_gemini(client, cfg, messages)
    else:
        return call_judge_openai(client, cfg, messages)


# ------------------------------- SCORE PROCESSING -------------------------------
def normalize_score(raw_score, is_baseline: bool = False) -> float:
    """Convert 1-5 score to 0-10 scale. Handle dict or scalar."""
    if isinstance(raw_score, dict):
        val = raw_score.get("baseline" if is_baseline else "candidate", 5)
    elif isinstance(raw_score, (int, float)):
        val = raw_score if not is_baseline else 5  # Assume baseline=5 for scalars
    else:
        val = 5
    return float(val) * 2  # Convert to 0-10 scale


def get_paired_scores(scores: Dict, metric: str) -> Tuple[float, float]:
    """Extract (candidate, baseline) scores on 0-10 scale."""
    raw = scores.get(metric, {})
    if isinstance(raw, dict):
        candidate = normalize_score(raw, is_baseline=False)
        baseline = normalize_score(raw, is_baseline=True)
    else:
        # Single value = candidate score, assume baseline = 10.0 (5*2)
        candidate = float(raw) * 2 if isinstance(raw, (int, float)) else 10.0
        baseline = 10.0
    return candidate, baseline


def interpret_score_diff(candidate: float, baseline: float, metric: str) -> str:
    """Generate short interpretation based on score difference."""
    diff = candidate - baseline
    
    # Special handling for verbosity (lower is better)
    if metric == "verbosity":
        diff = -diff  # Flip interpretation
    
    if diff >= 4:
        return "Strong win"
    elif diff >= 2:
        return "Clear advantage"
    elif diff >= 0.5:
        return "Slight edge"
    elif diff >= -0.5:
        return "Comparable"
    elif diff >= -2:
        return "Minor gap"
    elif diff >= -4:
        return "Notable weakness"
    else:
        return "Critical failure"


def compute_verdict_from_scores(scores: Dict) -> str:
    """
    Compute verdict from actual scores instead of trusting LLM's verdict.
    
    The LLM judge sometimes hallucinates the verdict field, saying "improved"
    when scores clearly show the candidate performed worse. This function
    computes the verdict based on the overall_quality score.
    
    Args:
        scores: Dict of metric -> {baseline: int, candidate: int}
    
    Returns:
        "improved", "regressed", or "equal"
    """
    overall = scores.get("overall_quality", {})
    if isinstance(overall, dict):
        baseline = overall.get("baseline", 3)
        candidate = overall.get("candidate", 3)
    else:
        # Fallback if not a dict
        return "equal"
    
    if candidate > baseline:
        return "improved"
    elif candidate < baseline:
        return "regressed"
    else:
        return "equal"


# ------------------------------- OUTPUT FORMATTING -------------------------------
def print_header(run_id: str, date_str: str, model_name: str, total: int):
    print("\n" + "=" * 80)
    print("                    LLM Judge Evaluation Results")
    print("=" * 80)
    print()
    print(f"Run ID          : {run_id}")
    print(f"Date            : {date_str}")
    print(f"Candidate Model : HOM-LLM(v2.0) ({model_name})")
    print(f"Baseline Model  : Cursor (Gemini 2.5 Flash)")
    print(f"Total Queries   : {total}")


def print_summary(records: List[Dict], run_id: str):
    verdicts = [r.get("verdict", "unknown") for r in records]
    improved = verdicts.count("improved")
    regressed = verdicts.count("regressed")
    equal = verdicts.count("equal")
    total = len(records)

    improved_pct = (improved / total * 100) if total else 0
    regressed_pct = (regressed / total * 100) if total else 0
    equal_pct = (equal / total * 100) if total else 0

    # Win rate = improved / (improved + regressed)
    contested = improved + regressed
    win_rate = (improved / contested * 100) if contested else 0

    print()
    print("-" * 22 + " SUMMARY " + "-" * 22)
    print(f"[+] Improved : {improved:3d} ({improved_pct:5.1f}%)")
    print(f"[-] Regressed: {regressed:3d} ({regressed_pct:5.1f}%)")
    print(f"[=] Equal    : {equal:3d} ({equal_pct:5.1f}%)")
    print()

    # Generate verdict
    if win_rate >= 80:
        verdict = "Strong performance advantage over baseline"
        strengths = "Consistent quality improvements across most queries"
        weaknesses = "Minor edge cases may need attention"
    elif win_rate >= 60:
        verdict = "Good performance, outperforming baseline"
        strengths = "Clear improvements in key areas"
        weaknesses = "Some regressions require investigation"
    elif win_rate >= 40:
        verdict = "Mixed results, roughly on par with baseline"
        strengths = "Competitive in several dimensions"
        weaknesses = "Inconsistent quality needs addressing"
    else:
        verdict = "Underperforming baseline - review required"
        strengths = "Some isolated improvements exist"
        weaknesses = "Systematic issues causing regressions"

    print(f"Overall Verdict: {verdict}")
    print(f"                  * {strengths}")
    print(f"                  * {weaknesses}")
    print()
    print(f"Candidate Win Rate (Improved / (Improved + Regressed)): {win_rate:.1f}%")


def print_score_table(scores: Dict, run_id: str, header: bool = True):
    """Print formatted score comparison table."""
    if header:
        print()
        print("-" * 27 + " SCORE COMPARISON (0-10) " + "-" * 27)
        print(f"{'Metric':<24} | {'HOM-LLM(v2.0)':<14} | {'Cursor Baseline':<15} | {'Interpretation':<20}")
        print("-" * 24 + "-+-" + "-" * 14 + "-+-" + "-" * 15 + "-+-" + "-" * 20)

    for metric in METRIC_ORDER:
        if metric not in scores:
            continue
        candidate, baseline = get_paired_scores(scores, metric)
        interp = interpret_score_diff(candidate, baseline, metric)
        display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
        print(f"{display_name:<24} | {candidate:>14.1f} | {baseline:>15.1f} | {interp:<20}")


def print_query_detail(record: Dict, run_id: str):
    """Print detailed per-query result."""
    qid = record.get("query_id")
    verdict = record.get("verdict", "unknown")
    scores = record.get("scores", {})
    explanation = record.get("explanation", "N/A")
    key_diffs = record.get("key_differences", [])

    verdict_icon = "[+]" if verdict == "improved" else "[-]" if verdict == "regressed" else "[=]"
    print()
    print(f"Query {qid} {verdict_icon} {verdict.upper()}")
    
    print_score_table(scores, run_id)

    print()
    print(f"Explanation:")
    print(f"  {explanation}")

    if key_diffs:
        print()
        print("Key Differences:")
        for diff in key_diffs:
            if isinstance(diff, str):
                print(f"  * {diff}")


def print_average_scores(records: List[Dict], run_id: str):
    """Print overall average scores across all queries."""
    print()
    print("-" * 20 + " OVERALL AVERAGE SCORES (0-10) " + "-" * 20)
    print(f"{'Metric':<24} | {'HOM-LLM(v2.0)':<14} | {'Cursor Baseline':<15} | {'Interpretation':<20}")
    print("-" * 24 + "-+-" + "-" * 14 + "-+-" + "-" * 15 + "-+-" + "-" * 20)

    for metric in METRIC_ORDER:
        candidate_vals = []
        baseline_vals = []
        for r in records:
            scores = r.get("scores", {})
            if metric in scores:
                c, b = get_paired_scores(scores, metric)
                candidate_vals.append(c)
                baseline_vals.append(b)

        if candidate_vals:
            avg_candidate = sum(candidate_vals) / len(candidate_vals)
            avg_baseline = sum(baseline_vals) / len(baseline_vals)
            interp = interpret_score_diff(avg_candidate, avg_baseline, metric)
            display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
            print(f"{display_name:<24} | {avg_candidate:>14.1f} | {avg_baseline:>15.1f} | {interp:<20}")


def print_final_summary(records: List[Dict]):
    """Print final interpretation summary."""
    # Compute overall metrics
    all_candidates = []
    all_baselines = []
    for r in records:
        scores = r.get("scores", {})
        for metric in METRIC_ORDER:
            if metric in scores:
                c, b = get_paired_scores(scores, metric)
                all_candidates.append(c)
                all_baselines.append(b)

    if all_candidates:
        avg_c = sum(all_candidates) / len(all_candidates)
        avg_b = sum(all_baselines) / len(all_baselines)
        diff = avg_c - avg_b

        if diff > 1:
            summary = (
                f"HOM-LLM demonstrates clear superiority with an average score advantage of {diff:.1f} points. "
                f"The system shows particular strength in semantic understanding and factual accuracy. "
                f"Continue current approach while monitoring edge cases."
            )
        elif diff > 0:
            summary = (
                f"HOM-LLM shows marginal improvement over baseline (+{diff:.1f} avg). "
                f"Performance is competitive but inconsistent across queries. "
                f"Focus on reducing variance and addressing regression cases."
            )
        else:
            summary = (
                f"HOM-LLM underperforms baseline by {abs(diff):.1f} points on average. "
                f"Critical review of context assembly and generation needed. "
                f"Prioritize fixing regressed queries before further development."
            )
    else:
        summary = "Insufficient data to generate summary."

    print()
    print("Final Summary Interpretation:")
    print(f"  {summary}")


# ------------------------------- MAIN -------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="LLM judge for HOM-LLM vs Cursor baseline.")
    parser.add_argument("--responses", type=Path, required=True, help="Path to responses JSONL from run_experiment")
    parser.add_argument("--baseline", type=Path, required=True, help="Path to cursor_baseline.json")
    parser.add_argument("--judge-config", type=Path, required=True, help="Path to judge_config.json")
    parser.add_argument("--output", type=Path, help="Optional output path for judge_results.jsonl")
    parser.add_argument(
        "--rpm", type=int, default=None,
        help="Rate limit: max requests per minute to LLM (overrides config, 0=unlimited)"
    )
    args = parser.parse_args()

    # Extract run_id from responses path
    run_id = args.responses.parent.name

    responses = read_jsonl(args.responses)
    baseline_payload = read_json(args.baseline)
    baseline_map = {item["query_id"]: item for item in baseline_payload.get("queries", [])}

    cfg = load_judge_config(args.judge_config)

    if cfg.provider == "gemini":
        client = ensure_gemini_client(cfg)
    else:
        client = ensure_openai_client(cfg)

    output_path = args.output or args.responses.parent / "judge_results.jsonl"

    # Initialize rate limiter
    # CLI --rpm overrides config file setting
    rpm = args.rpm if args.rpm is not None else cfg.requests_per_minute
    rate_limiter = RateLimiter(requests_per_minute=rpm)
    if rate_limiter.enabled:
        print(f"Rate limit: {rpm} requests/minute ({60.0/rpm:.1f}s between requests)")
    else:
        print("Rate limit: disabled (unlimited)")

    # Collect all records
    records: List[Dict] = []
    model_name = "unknown"

    print(f"\nJudging {len(responses)} queries...")

    for idx, resp in enumerate(responses, 1):
        qid = resp.get("query_id")
        model_name = resp.get("model_name", model_name)

        base = baseline_map.get(qid)
        if not base:
            sys.stderr.write(f"[WARN] Missing baseline for query_id {qid}, skipping.\n")
            continue

        print(f"  [{idx}/{len(responses)}] Query {qid}...", end=" ", flush=True)

        messages = build_prompt(
            baseline_answer=base.get("answer", ""),
            candidate_answer=resp.get("answer_text", ""),
            query_text=resp.get("query_text", ""),
        )

        try:
            # Apply rate limiting before each LLM call
            wait_time = rate_limiter.acquire()
            if wait_time > 0:
                # Show wait indicator for long waits
                if wait_time > 1.0:
                    print(f"(waited {wait_time:.1f}s) ", end="", flush=True)
            
            judged = call_judge(client, cfg, messages)
            # IMPORTANT: Compute verdict from scores, not LLM's verdict field.
            # The LLM sometimes hallucinates the verdict, saying "improved" when
            # the scores clearly show the candidate performed worse.
            scores = judged.get("scores", {})
            verdict = compute_verdict_from_scores(scores)
            llm_verdict = judged.get("verdict", "unknown")
            if verdict != llm_verdict:
                # Log when we override the LLM's verdict
                sys.stderr.write(f"[WARN] Query {qid}: LLM said '{llm_verdict}' but scores show '{verdict}'\n")
            verdict_symbol = '[+]' if verdict == 'improved' else '[-]' if verdict == 'regressed' else '[=]'
            print(f"{verdict_symbol} {verdict}")
        except Exception as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            continue

        record = {
            "query_id": qid,
            "query_text": resp.get("query_text"),
            "candidate_model": resp.get("model_name"),
            "candidate_provider": resp.get("provider"),
            "baseline_system": baseline_payload.get("metadata", {}).get("system", "Cursor"),
            "judge_model": cfg.model,
            "scores": scores,
            "verdict": verdict,  # Use computed verdict, not LLM's
            "llm_verdict": llm_verdict,  # Store LLM's original verdict for audit
            "explanation": judged.get("explanation"),
            "key_differences": judged.get("key_differences"),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records.append(record)
        write_jsonl(output_path, [record])

    if not records:
        print("\nNo queries were judged successfully.")
        return

    # Format date
    date_str = datetime.now().strftime("%B %d, %Y")

    # ====================== PRINT FULL REPORT ======================
    print_header(run_id, date_str, model_name, len(records))
    print_summary(records, run_id)

    # Separate by verdict
    regressed = [r for r in records if r.get("verdict") == "regressed"]
    improved = [r for r in records if r.get("verdict") == "improved"]
    equal = [r for r in records if r.get("verdict") == "equal"]

    # Print regressions first (priority)
    if regressed:
        print()
        print()
        print("-" * 18 + " DETAILED PER-QUERY RESULTS " + "-" * 18)
        print()
        print("=== CRITICAL REGRESSIONS (Review First) ===")
        for r in regressed:
            print_query_detail(r, run_id)

    # Then improvements
    if improved:
        print()
        print("=== IMPROVEMENTS ===")
        for r in improved:
            print_query_detail(r, run_id)

    # Equal last (optional)
    if equal:
        print()
        print("=== EQUAL ===")
        for r in equal:
            print_query_detail(r, run_id)

    # Overall averages
    print_average_scores(records, run_id)

    # Final interpretation
    print_final_summary(records)

    # Footer
    print()
    print("=" * 80)
    print(f"Judgment results saved to: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()


