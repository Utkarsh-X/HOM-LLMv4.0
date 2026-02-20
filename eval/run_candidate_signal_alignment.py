"""Candidate-level signal alignment audit for ranking scores.

This script evaluates whether ranking signals (base/rerank/final) align with
LLM-judged candidate relevance at the per-query candidate level.

It does NOT modify ranking logic.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

# Reuse existing judge client plumbing.
from run_judge import RateLimiter, call_judge, ensure_client, load_judge_config


@dataclass
class CandidateRecord:
    doc_id: str
    file: str
    base_score: float
    rerank_score: float
    final_score: float
    content: str
    span_start: int | None = None
    span_end: int | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def kendall_tau_b(scores_a: dict[str, float], scores_b: dict[str, float]) -> float | None:
    """Compute Kendall tau-b with tie handling."""
    ids = sorted(set(scores_a.keys()) & set(scores_b.keys()))
    n = len(ids)
    if n < 2:
        return None

    concordant = 0
    discordant = 0
    ties_a = 0
    ties_b = 0

    for i in range(n):
        for j in range(i + 1, n):
            a1 = scores_a[ids[i]]
            a2 = scores_a[ids[j]]
            b1 = scores_b[ids[i]]
            b2 = scores_b[ids[j]]

            da = sign(a1 - a2)
            db = sign(b1 - b2)

            if da == 0 and db == 0:
                continue
            if da == 0:
                ties_a += 1
                continue
            if db == 0:
                ties_b += 1
                continue
            if da == db:
                concordant += 1
            else:
                discordant += 1

    denom = math.sqrt((concordant + discordant + ties_a) * (concordant + discordant + ties_b))
    if denom == 0:
        return None
    return (concordant - discordant) / denom


def normalized_entropy(values: list[float]) -> float:
    """Normalized Shannon entropy in [0,1]."""
    if not values:
        return 0.0
    total = sum(values)
    if total <= 0:
        return 0.0
    probs = [v / total for v in values if v > 0]
    if not probs:
        return 0.0
    n = len(probs)
    if n <= 1:
        return 0.0
    h = -sum(p * math.log(p) for p in probs)
    return h / math.log(n)


def precision_at_k(pred_order: list[str], gold_order: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    pred = pred_order[:k]
    gold = set(gold_order[:k])
    if not pred:
        return 0.0
    return len([d for d in pred if d in gold]) / float(k)


def build_prompt(query_text: str, candidates: list[CandidateRecord], content_chars: int) -> list[dict[str, str]]:
    system_msg = (
        "You are grading candidate code snippets for query relevance.\n"
        "Return ONLY valid JSON.\n"
        "Score each candidate independently on relevance to the query:\n"
        "0 = irrelevant, 10 = directly answers the query with high evidence.\n"
        "Do not use ties unless evidence is truly equal.\n"
    )

    lines: list[str] = []
    lines.append("QUERY:")
    lines.append(query_text.strip())
    lines.append("")
    lines.append("CANDIDATES:")
    for idx, c in enumerate(candidates, start=1):
        excerpt = (c.content or "").strip()
        if len(excerpt) > content_chars:
            excerpt = excerpt[:content_chars] + "..."
        lines.append(f"[{idx}] doc_id={c.doc_id}")
        lines.append(f"file={c.file}")
        if c.span_start is not None and c.span_end is not None:
            lines.append(f"span={c.span_start}:{c.span_end}")
        lines.append("snippet:")
        lines.append(excerpt if excerpt else "(no content)")
        lines.append("")

    lines.append("Return JSON with this exact shape:")
    lines.append("{")
    lines.append('  "labels": [')
    lines.append('    {"doc_id": "string", "relevance": 0-10, "rationale": "short"}')
    lines.append("  ]")
    lines.append("}")
    lines.append("Include exactly one label for every candidate doc_id shown above.")
    user_msg = "\n".join(lines)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def parse_labels(raw: dict[str, Any], expected_doc_ids: list[str]) -> tuple[dict[str, float], dict[str, str]]:
    scores: dict[str, float] = {}
    rationales: dict[str, str] = {}

    labels = raw.get("labels")
    if isinstance(labels, list):
        for item in labels:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("doc_id", "")).strip()
            if not doc_id:
                continue
            rel = item.get("relevance", 0)
            try:
                score = float(rel)
            except Exception:
                continue
            scores[doc_id] = clamp(score, 0.0, 10.0)
            rationale = str(item.get("rationale", "")).strip()
            if rationale:
                rationales[doc_id] = rationale
    elif isinstance(labels, dict):
        # fallback: {"doc_id": score, ...}
        for doc_id, rel in labels.items():
            try:
                score = float(rel)
            except Exception:
                continue
            scores[str(doc_id)] = clamp(score, 0.0, 10.0)

    # Fill missing docs deterministically with 0.0
    for doc_id in expected_doc_ids:
        if doc_id not in scores:
            scores[doc_id] = 0.0
    return scores, rationales


def ordered_doc_ids(score_map: dict[str, float]) -> list[str]:
    return [doc_id for doc_id, _ in sorted(score_map.items(), key=lambda kv: (-kv[1], kv[0]))]


def mean_or_none(values: list[float | None]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return (sum(nums) / len(nums)) if nums else None


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(max(0, min(len(sorted_vals) - 1, round((len(sorted_vals) - 1) * p))))
    return sorted_vals[idx]


def _resolve_candidate_payload(con: duckdb.DuckDBPyConnection, doc_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not doc_ids:
        return {}
    unique_doc_ids = list(dict.fromkeys(doc_ids))
    placeholders = ", ".join(["?"] * len(unique_doc_ids))
    out: dict[str, dict[str, Any]] = {}

    # 1) Preferred path: chunk IDs.
    chunk_rows = con.execute(
        f"""
        SELECT chunk_id, file_path, content, span_start, span_end
        FROM chunks
        WHERE chunk_id IN ({placeholders})
        """,
        unique_doc_ids,
    ).fetchall()
    for chunk_id, file_path, content, span_start, span_end in chunk_rows:
        out[str(chunk_id)] = {
            "file": str(file_path or ""),
            "content": str(content or ""),
            "span_start": span_start,
            "span_end": span_end,
        }

    unresolved = [doc_id for doc_id in unique_doc_ids if doc_id not in out]
    if not unresolved:
        return out

    # 2) Legacy path: symbol IDs (or file_id:symbol_id format).
    resolved_symbol_ids = [doc_id.split(":", 1)[1] if ":" in doc_id else doc_id for doc_id in unresolved]
    sym_placeholders = ", ".join(["?"] * len(resolved_symbol_ids))
    sym_rows = con.execute(
        f"""
        SELECT s.symbol_id, f.path, s.content, s.start_line, s.end_line
        FROM symbols s
        LEFT JOIN files f ON s.file_id = f.file_id
        WHERE s.symbol_id IN ({sym_placeholders})
        """,
        resolved_symbol_ids,
    ).fetchall()
    by_symbol = {
        str(symbol_id): {
            "file": str(file_path or ""),
            "content": str(content or ""),
            "span_start": start_line,
            "span_end": end_line,
        }
        for symbol_id, file_path, content, start_line, end_line in sym_rows
    }
    for doc_id in unresolved:
        symbol_id = doc_id.split(":", 1)[1] if ":" in doc_id else doc_id
        if symbol_id in by_symbol:
            out[doc_id] = by_symbol[symbol_id]
    return out


def load_candidates_for_query(
    run_id: str,
    top_k: int,
    con: duckdb.DuckDBPyConnection,
) -> list[CandidateRecord]:
    diag_path = Path("artifacts") / "runs" / run_id / "candidate_diagnostics.json"
    if not diag_path.exists():
        return []

    payload = json.loads(diag_path.read_text(encoding="utf-8"))
    ranking = payload.get("ranking_top20") or []
    ranking = [r for r in ranking if isinstance(r, dict)]
    ranking = ranking[:top_k]
    if not ranking:
        return []

    doc_ids = [str(r.get("doc_id")) for r in ranking if r.get("doc_id")]
    data_map = _resolve_candidate_payload(con, doc_ids)

    out: list[CandidateRecord] = []
    for r in ranking:
        doc_id = str(r.get("doc_id", "")).strip()
        if not doc_id:
            continue
        data = data_map.get(doc_id) or {}
        out.append(
            CandidateRecord(
                doc_id=doc_id,
                file=str(r.get("file", data.get("file", ""))),
                base_score=float(r.get("base_score", 0.0) or 0.0),
                rerank_score=float(r.get("rerank_score", 0.0) or 0.0),
                final_score=float(r.get("final_score", 0.0) or 0.0),
                content=str(data.get("content", "") or ""),
                span_start=data.get("span_start"),
                span_end=data.get("span_end"),
            )
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run candidate-level signal alignment audit.")
    parser.add_argument("--responses", type=Path, required=True, help="Path to responses jsonl (e.g. stage2 responses_clean20.jsonl)")
    parser.add_argument("--judge-config", type=Path, required=True, help="Judge config JSON path")
    parser.add_argument("--provider", type=str, default=None, help="Optional judge provider override")
    parser.add_argument("--duckdb-path", type=Path, default=Path("indexes/metadata.duckdb"))
    parser.add_argument("--top-k", type=int, default=20, help="Candidates per query (15-20 recommended)")
    parser.add_argument("--content-chars", type=int, default=1400, help="Max chars per candidate snippet in judge prompt")
    parser.add_argument("--output-prefix", type=Path, required=True, help="Output prefix path without extension")
    parser.add_argument("--rpm", type=int, default=None, help="Override judge requests/min")
    parser.add_argument("--resume", action="store_true", help="Resume from existing labels jsonl")
    args = parser.parse_args()

    responses = read_jsonl(args.responses)
    responses_by_qid = {int(r["query_id"]): r for r in responses if "query_id" in r}
    query_ids = sorted(responses_by_qid.keys())

    cfg = load_judge_config(args.judge_config, provider_override=args.provider)
    if args.rpm is not None:
        cfg.requests_per_minute = int(args.rpm)

    client = ensure_client(cfg)
    limiter = RateLimiter(requests_per_minute=cfg.requests_per_minute)

    labels_jsonl = Path(str(args.output_prefix) + "_labels.jsonl")
    summary_json = Path(str(args.output_prefix) + "_summary.json")
    summary_md = Path(str(args.output_prefix) + "_summary.md")

    existing_rows: list[dict[str, Any]] = []
    existing_by_qid: dict[int, dict[str, Any]] = {}
    if args.resume and labels_jsonl.exists():
        existing_rows = read_jsonl(labels_jsonl)
        existing_by_qid = {int(r["query_id"]): r for r in existing_rows if "query_id" in r}

    con = duckdb.connect(str(args.duckdb_path), read_only=True)

    label_rows: list[dict[str, Any]] = []
    done = 0
    total = len(query_ids)
    for qid in query_ids:
        if qid in existing_by_qid:
            label_rows.append(existing_by_qid[qid])
            done += 1
            continue

        resp = responses_by_qid[qid]
        query_text = str(resp.get("query_text", "")).strip()
        run_id = str(resp.get("run_id", "")).strip()

        candidates = load_candidates_for_query(run_id, args.top_k, con)
        if not candidates:
            label_rows.append(
                {
                    "query_id": qid,
                    "query_text": query_text,
                    "run_id": run_id,
                    "status": "ERROR",
                    "error": "No candidate diagnostics found",
                }
            )
            done += 1
            print(f"[{done}/{total}] Q{qid}: no candidates", flush=True)
            continue

        messages = build_prompt(query_text, candidates, content_chars=args.content_chars)
        limiter.acquire()
        try:
            judged, used_model = call_judge(client, cfg, messages)
            expected_doc_ids = [c.doc_id for c in candidates]
            judged_scores, rationales = parse_labels(judged, expected_doc_ids)

            row = {
                "query_id": qid,
                "query_text": query_text,
                "run_id": run_id,
                "status": "OK",
                "judge_provider": cfg.provider,
                "judge_model_config": cfg.model,
                "judge_model_used": used_model,
                "candidates": [
                    {
                        "doc_id": c.doc_id,
                        "file": c.file,
                        "base_score": c.base_score,
                        "rerank_score": c.rerank_score,
                        "final_score": c.final_score,
                        "judged_relevance": judged_scores.get(c.doc_id, 0.0),
                        "rationale": rationales.get(c.doc_id, ""),
                    }
                    for c in candidates
                ],
            }
            label_rows.append(row)
            done += 1
            print(f"[{done}/{total}] Q{qid}: labeled {len(candidates)} candidates", flush=True)
        except Exception as exc:
            label_rows.append(
                {
                    "query_id": qid,
                    "query_text": query_text,
                    "run_id": run_id,
                    "status": "ERROR",
                    "error": str(exc),
                }
            )
            done += 1
            print(f"[{done}/{total}] Q{qid}: ERROR {exc}", flush=True)

        # Incremental write for recoverability
        with labels_jsonl.open("w", encoding="utf-8") as f:
            for rec in sorted(label_rows, key=lambda r: int(r.get("query_id", 0))):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Metrics
    per_query: list[dict[str, Any]] = []
    for row in sorted(label_rows, key=lambda r: int(r.get("query_id", 0))):
        qid = int(row.get("query_id"))
        if row.get("status") != "OK":
            per_query.append(
                {
                    "query_id": qid,
                    "status": row.get("status"),
                    "error": row.get("error"),
                }
            )
            continue

        candidates = row["candidates"]
        base = {c["doc_id"]: float(c["base_score"]) for c in candidates}
        rerank = {c["doc_id"]: float(c["rerank_score"]) for c in candidates}
        final = {c["doc_id"]: float(c["final_score"]) for c in candidates}
        judged = {c["doc_id"]: float(c["judged_relevance"]) for c in candidates}

        base_order = ordered_doc_ids(base)
        rerank_order = ordered_doc_ids(rerank)
        final_order = ordered_doc_ids(final)
        judged_order = ordered_doc_ids(judged)

        top_rerank = rerank_order[0] if rerank_order else None
        top_judged = judged_order[0] if judged_order else None

        rerank_pos = [v for v in rerank.values() if v > 0]
        rerank_entropy = normalized_entropy(rerank_pos)
        rerank_std = statistics.pstdev(rerank_pos) if rerank_pos else 0.0

        per_query.append(
            {
                "query_id": qid,
                "status": "OK",
                "candidate_count": len(candidates),
                "highest_rerank_doc_id": top_rerank,
                "highest_judged_doc_id": top_judged,
                "top_rerank_matches_top_judged": top_rerank == top_judged,
                "kendall_tau": {
                    "base_vs_judged": kendall_tau_b(base, judged),
                    "rerank_vs_judged": kendall_tau_b(rerank, judged),
                    "final_vs_judged": kendall_tau_b(final, judged),
                },
                "precision_at_1": {
                    "base": precision_at_k(base_order, judged_order, 1),
                    "rerank": precision_at_k(rerank_order, judged_order, 1),
                    "final": precision_at_k(final_order, judged_order, 1),
                },
                "precision_at_3": {
                    "base": precision_at_k(base_order, judged_order, 3),
                    "rerank": precision_at_k(rerank_order, judged_order, 3),
                    "final": precision_at_k(final_order, judged_order, 3),
                },
                "rerank_entropy": rerank_entropy,
                "rerank_std": rerank_std,
                "candidates": candidates,
            }
        )

    ok_rows = [r for r in per_query if r.get("status") == "OK"]

    mean_tau_rerank = mean_or_none([r["kendall_tau"]["rerank_vs_judged"] for r in ok_rows])
    mean_tau_base = mean_or_none([r["kendall_tau"]["base_vs_judged"] for r in ok_rows])
    mean_tau_final = mean_or_none([r["kendall_tau"]["final_vs_judged"] for r in ok_rows])

    def pct(count: int, total_n: int) -> float:
        return (100.0 * count / total_n) if total_n else 0.0

    rerank_p1_gt_base = [r for r in ok_rows if r["precision_at_1"]["rerank"] > r["precision_at_1"]["base"]]
    rerank_p1_lt_base = [r for r in ok_rows if r["precision_at_1"]["rerank"] < r["precision_at_1"]["base"]]
    rerank_p1_eq_base = [r for r in ok_rows if r["precision_at_1"]["rerank"] == r["precision_at_1"]["base"]]

    ent_vals = sorted([float(r["rerank_entropy"]) for r in ok_rows])
    std_vals = sorted([float(r["rerank_std"]) for r in ok_rows])
    ent_cut = percentile(ent_vals, 0.5) if ent_vals else 0.0
    std_cut = percentile(std_vals, 0.5) if std_vals else 0.0

    low_entropy = [r for r in ok_rows if float(r["rerank_entropy"]) <= ent_cut]
    high_entropy = [r for r in ok_rows if float(r["rerank_entropy"]) > ent_cut]
    flat = [r for r in ok_rows if float(r["rerank_std"]) <= std_cut]
    non_flat = [r for r in ok_rows if float(r["rerank_std"]) > std_cut]

    def cohort_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "count": len(rows),
            "mean_tau_base_vs_judged": mean_or_none([r["kendall_tau"]["base_vs_judged"] for r in rows]),
            "mean_tau_rerank_vs_judged": mean_or_none([r["kendall_tau"]["rerank_vs_judged"] for r in rows]),
            "mean_tau_final_vs_judged": mean_or_none([r["kendall_tau"]["final_vs_judged"] for r in rows]),
            "mean_p1_base": mean_or_none([r["precision_at_1"]["base"] for r in rows]),
            "mean_p1_rerank": mean_or_none([r["precision_at_1"]["rerank"] for r in rows]),
            "mean_p1_final": mean_or_none([r["precision_at_1"]["final"] for r in rows]),
            "mean_p3_base": mean_or_none([r["precision_at_3"]["base"] for r in rows]),
            "mean_p3_rerank": mean_or_none([r["precision_at_3"]["rerank"] for r in rows]),
            "mean_p3_final": mean_or_none([r["precision_at_3"]["final"] for r in rows]),
        }

    aggregate = {
        "queries_total": len(query_ids),
        "queries_ok": len(ok_rows),
        "queries_error": len(query_ids) - len(ok_rows),
        "mean_kendall_tau": {
            "base_vs_judged": mean_tau_base,
            "rerank_vs_judged": mean_tau_rerank,
            "final_vs_judged": mean_tau_final,
        },
        "mean_precision_at_1": {
            "base": mean_or_none([r["precision_at_1"]["base"] for r in ok_rows]),
            "rerank": mean_or_none([r["precision_at_1"]["rerank"] for r in ok_rows]),
            "final": mean_or_none([r["precision_at_1"]["final"] for r in ok_rows]),
        },
        "mean_precision_at_3": {
            "base": mean_or_none([r["precision_at_3"]["base"] for r in ok_rows]),
            "rerank": mean_or_none([r["precision_at_3"]["rerank"] for r in ok_rows]),
            "final": mean_or_none([r["precision_at_3"]["final"] for r in ok_rows]),
        },
        "rerank_p1_vs_base": {
            "gt_count": len(rerank_p1_gt_base),
            "lt_count": len(rerank_p1_lt_base),
            "eq_count": len(rerank_p1_eq_base),
            "gt_pct": pct(len(rerank_p1_gt_base), len(ok_rows)),
            "lt_pct": pct(len(rerank_p1_lt_base), len(ok_rows)),
            "eq_pct": pct(len(rerank_p1_eq_base), len(ok_rows)),
        },
        "top_rerank_matches_top_judged_pct": pct(
            len([r for r in ok_rows if r["top_rerank_matches_top_judged"]]),
            len(ok_rows),
        ),
        "cohorts": {
            "low_entropy": {"threshold_median": ent_cut, **cohort_summary(low_entropy)},
            "high_entropy": {"threshold_median": ent_cut, **cohort_summary(high_entropy)},
            "flat_rerank": {"std_threshold_median": std_cut, **cohort_summary(flat)},
            "non_flat_rerank": {"std_threshold_median": std_cut, **cohort_summary(non_flat)},
        },
    }

    out = {
        "config": {
            "responses": str(args.responses),
            "judge_config": str(args.judge_config),
            "provider": cfg.provider,
            "judge_model_config": cfg.model,
            "top_k": args.top_k,
            "content_chars": args.content_chars,
            "duckdb_path": str(args.duckdb_path),
        },
        "aggregate": aggregate,
        "per_query": per_query,
    }
    summary_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines: list[str] = []
    md_lines.append("# Candidate-Level Signal Alignment Audit")
    md_lines.append("")
    md_lines.append("## Aggregate")
    md_lines.append(f"- queries_ok: {aggregate['queries_ok']} / {aggregate['queries_total']}")
    md_lines.append(
        f"- mean Kendall tau (base vs judged): {aggregate['mean_kendall_tau']['base_vs_judged']}"
    )
    md_lines.append(
        f"- mean Kendall tau (rerank vs judged): {aggregate['mean_kendall_tau']['rerank_vs_judged']}"
    )
    md_lines.append(
        f"- mean Kendall tau (final vs judged): {aggregate['mean_kendall_tau']['final_vs_judged']}"
    )
    md_lines.append(
        f"- rerank P@1 > base P@1: {aggregate['rerank_p1_vs_base']['gt_pct']:.1f}% "
        f"({aggregate['rerank_p1_vs_base']['gt_count']}/{aggregate['queries_ok']})"
    )
    md_lines.append(
        f"- rerank P@1 < base P@1: {aggregate['rerank_p1_vs_base']['lt_pct']:.1f}% "
        f"({aggregate['rerank_p1_vs_base']['lt_count']}/{aggregate['queries_ok']})"
    )
    md_lines.append(
        f"- rerank P@1 == base P@1: {aggregate['rerank_p1_vs_base']['eq_pct']:.1f}% "
        f"({aggregate['rerank_p1_vs_base']['eq_count']}/{aggregate['queries_ok']})"
    )
    md_lines.append("")
    md_lines.append("## Per Query")
    md_lines.append(
        "| Query | Status | top-rerank==top-judged | tau(base,judge) | tau(rerank,judge) | tau(final,judge) | P@1 base/rerank/final | P@3 base/rerank/final |"
    )
    md_lines.append("|---|---|---|---:|---:|---:|---|---|")
    for r in per_query:
        if r.get("status") != "OK":
            md_lines.append(
                f"| {r['query_id']} | ERROR | - | - | - | - | - | - |"
            )
            continue
        md_lines.append(
            f"| {r['query_id']} | OK | {r['top_rerank_matches_top_judged']} | "
            f"{r['kendall_tau']['base_vs_judged']} | {r['kendall_tau']['rerank_vs_judged']} | {r['kendall_tau']['final_vs_judged']} | "
            f"{r['precision_at_1']['base']:.3f}/{r['precision_at_1']['rerank']:.3f}/{r['precision_at_1']['final']:.3f} | "
            f"{r['precision_at_3']['base']:.3f}/{r['precision_at_3']['rerank']:.3f}/{r['precision_at_3']['final']:.3f} |"
        )
    summary_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Saved labels: {labels_jsonl}")
    print(f"Saved summary json: {summary_json}")
    print(f"Saved summary md: {summary_md}")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
