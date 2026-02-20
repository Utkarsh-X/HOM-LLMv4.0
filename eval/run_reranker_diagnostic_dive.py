"""Reranker diagnostic deep dive (analysis-only, no scoring changes)."""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from homllm.ranking.reranker import QwenReranker  # noqa: E402


STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "how",
    "what",
    "when",
    "where",
    "why",
    "does",
    "do",
    "is",
    "are",
    "be",
    "this",
    "that",
    "it",
    "as",
    "by",
    "from",
}


@dataclass
class CandidateContext:
    doc_id: str
    file: str
    content: str
    span_start: int | None
    span_end: int | None
    vector_score: float | None = None
    bm25_score: float | None = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def normalize_text_tokens(text: str) -> set[str]:
    toks = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
    return {t for t in toks if t not in STOPWORDS}


def overlap_ratio(query: str, chunk: str) -> float:
    q = normalize_text_tokens(query)
    if not q:
        return 0.0
    c = normalize_text_tokens(chunk)
    return len(q & c) / float(len(q))


def file_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return suffix if suffix else "<none>"


def percentile_rank(values: list[float], value: float) -> float | None:
    if not values:
        return None
    below_or_equal = sum(1 for v in values if v <= value)
    return below_or_equal / float(len(values))


def _resolve_candidate_payload(con: duckdb.DuckDBPyConnection, doc_ids: list[str]) -> dict[str, CandidateContext]:
    if not doc_ids:
        return {}
    unique_doc_ids = list(dict.fromkeys(doc_ids))
    placeholders = ", ".join(["?"] * len(unique_doc_ids))
    out: dict[str, CandidateContext] = {}

    chunk_rows = con.execute(
        f"""
        SELECT chunk_id, file_path, content, span_start, span_end
        FROM chunks
        WHERE chunk_id IN ({placeholders})
        """,
        unique_doc_ids,
    ).fetchall()
    for chunk_id, file_path, content, span_start, span_end in chunk_rows:
        doc_id = str(chunk_id)
        out[doc_id] = CandidateContext(
            doc_id=doc_id,
            file=str(file_path or ""),
            content=str(content or ""),
            span_start=span_start,
            span_end=span_end,
        )

    unresolved = [doc_id for doc_id in unique_doc_ids if doc_id not in out]
    if not unresolved:
        return out

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
        str(symbol_id): CandidateContext(
            doc_id="",
            file=str(file_path or ""),
            content=str(content or ""),
            span_start=start_line,
            span_end=end_line,
        )
        for symbol_id, file_path, content, start_line, end_line in sym_rows
    }
    for doc_id in unresolved:
        symbol_id = doc_id.split(":", 1)[1] if ":" in doc_id else doc_id
        if symbol_id in by_symbol:
            ctx = by_symbol[symbol_id]
            out[doc_id] = CandidateContext(
                doc_id=doc_id,
                file=ctx.file,
                content=ctx.content,
                span_start=ctx.span_start,
                span_end=ctx.span_end,
            )
    return out


def classify_query_type(query: str) -> str:
    q = query.lower()
    bug_markers = [
        "bug",
        "fix",
        "error",
        "nan",
        "timeout",
        "fail",
        "failure",
        "retry",
        "fallback",
        "circular",
        "infinite loop",
    ]
    if any(m in q for m in bug_markers):
        return "bug-fix"
    if re.search(r"[A-Z][a-zA-Z0-9_]*|[a-z]+_[a-z0-9_]+", query):
        return "api-lookup"
    return "explanation"


def short_diff(a: str, b: str, max_lines: int = 200) -> list[str]:
    diff = list(
        difflib.unified_diff(
            (a or "").splitlines(),
            (b or "").splitlines(),
            fromfile="judged_top",
            tofile="rerank_top",
            lineterm="",
            n=2,
        )
    )
    if len(diff) <= max_lines:
        return diff
    return diff[:max_lines] + [f"... truncated {len(diff) - max_lines} diff lines ..."]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reranker diagnostic deep dive.")
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path(
            "eval/runs/stage2_geometry_lock_only_flags_repro/candidate_signal_alignment_labels.jsonl"
        ),
    )
    parser.add_argument(
        "--responses",
        type=Path,
        default=Path("eval/runs/stage2_geometry_lock_only_flags_repro/responses_clean20.jsonl"),
    )
    parser.add_argument("--duckdb-path", type=Path, default=Path("indexes/metadata.duckdb"))
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("eval/runs/stage2_geometry_lock_only_flags_repro/reranker_diagnostic_dive"),
    )
    parser.add_argument("--reranker-model", type=str, default="Qwen/Qwen3-Reranker-0.6B")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--max-input-chars", type=int, default=10000)
    args = parser.parse_args()

    labels = [r for r in read_jsonl(args.labels) if r.get("status") == "OK"]
    responses = {int(r["query_id"]): r for r in read_jsonl(args.responses) if "query_id" in r}
    labels_by_q = {int(r["query_id"]): r for r in labels if "query_id" in r}
    query_ids = sorted(set(labels_by_q.keys()) & set(responses.keys()))

    con = duckdb.connect(str(args.duckdb_path), read_only=True)
    reranker = QwenReranker(args.reranker_model)
    if not reranker.healthcheck():
        raise RuntimeError("Reranker healthcheck failed; cannot run diagnostic deep dive.")

    out_json = Path(str(args.output_prefix) + ".json")
    out_md = Path(str(args.output_prefix) + ".md")

    per_query: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []
    top1_rerank_lengths: list[int] = []
    top1_judged_lengths: list[int] = []
    top1_rerank_overlaps: list[float] = []
    top1_judged_overlaps: list[float] = []

    for idx, qid in enumerate(query_ids, start=1):
        row = labels_by_q[qid]
        query = str(row.get("query_text", "")).strip()
        run_id = str(row.get("run_id", "")).strip()

        # Candidate list from judged file (already aligned with stage2 run)
        raw_candidates = [c for c in row.get("candidates", []) if isinstance(c, dict)]
        doc_ids = [str(c.get("doc_id", "")) for c in raw_candidates if c.get("doc_id")]
        payload_map = _resolve_candidate_payload(con, doc_ids)

        # Enrich with retrieval vector/bm25 from candidate diagnostics retrieval_top20
        vector_map: dict[str, float] = {}
        bm25_map: dict[str, float] = {}
        diag_path = Path("artifacts") / "runs" / run_id / "candidate_diagnostics.json"
        if diag_path.exists():
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            for r in diag.get("retrieval_top20", []) or []:
                if not isinstance(r, dict):
                    continue
                doc_id = str(r.get("doc_id", ""))
                if not doc_id:
                    continue
                vs = r.get("vector_score")
                bs = r.get("bm25_score")
                if isinstance(vs, (int, float)):
                    vector_map[doc_id] = float(vs)
                if isinstance(bs, (int, float)):
                    bm25_map[doc_id] = float(bs)

        candidates: list[dict[str, Any]] = []
        for c in raw_candidates:
            doc_id = str(c.get("doc_id", ""))
            if not doc_id:
                continue
            ctx = payload_map.get(doc_id)
            content = ctx.content if ctx else ""
            file_path = ctx.file if ctx and ctx.file else str(c.get("file", ""))
            base_score = float(c.get("base_score", 0.0) or 0.0)
            rerank_score = float(c.get("rerank_score", 0.0) or 0.0)
            final_score = float(c.get("final_score", 0.0) or 0.0)
            judged = float(c.get("judged_relevance", 0.0) or 0.0)
            chunk_overlap = overlap_ratio(query, content)
            pair_text = f"{query} [SEP] {content}" if content else f"{query} [SEP] {doc_id}"
            if len(pair_text) > args.max_input_chars:
                pair_text = pair_text[: args.max_input_chars] + "...<truncated_for_report>"

            candidates.append(
                {
                    "doc_id": doc_id,
                    "file": file_path,
                    "content": content,
                    "span_start": ctx.span_start if ctx else None,
                    "span_end": ctx.span_end if ctx else None,
                    "base_score": base_score,
                    "rerank_score": rerank_score,
                    "final_score": final_score,
                    "judged_relevance": judged,
                    "vector_score": vector_map.get(doc_id),
                    "bm25_score": bm25_map.get(doc_id),
                    "overlap_with_query_terms": chunk_overlap,
                    "rerank_input_text": pair_text,
                }
            )

        # Compute raw rerank logits with same internals used by pipeline (pre min-max).
        documents = [c["content"] if c["content"] else c["doc_id"] for c in candidates]
        if reranker._device == "cuda":
            raw_scores = reranker._batch_score_gpu(query, documents)
        else:
            raw_scores = reranker._batch_score_cpu(query, documents)

        # Add token-length diagnostics.
        max_vector = max(vector_map.values()) if vector_map else None
        for c, raw in zip(candidates, raw_scores):
            c["rerank_raw_score"] = float(raw)
            doc_tokens = reranker._tokenizer(
                c["content"] if c["content"] else c["doc_id"],
                add_special_tokens=False,
                truncation=False,
                return_attention_mask=False,
            )["input_ids"]
            pair_full = reranker._tokenizer(
                f"{query} [SEP] {c['content'] if c['content'] else c['doc_id']}",
                add_special_tokens=True,
                truncation=False,
                return_attention_mask=False,
            )["input_ids"]
            pair_trunc = reranker._tokenizer(
                f"{query} [SEP] {c['content'] if c['content'] else c['doc_id']}",
                add_special_tokens=True,
                truncation=True,
                max_length=512,
                return_attention_mask=False,
            )["input_ids"]
            c["chunk_token_length"] = int(len(doc_tokens))
            c["pair_token_length_full"] = int(len(pair_full))
            c["pair_token_length_after_trunc"] = int(len(pair_trunc))
            c["pair_was_truncated"] = len(pair_full) > 512
            c["file_type"] = file_type(c["file"])
            c["dense_percentile"] = (
                (c["vector_score"] / max_vector) if (max_vector and c["vector_score"] is not None and max_vector > 0) else None
            )

        base_sorted = sorted(candidates, key=lambda x: (-x["base_score"], x["doc_id"]))
        rerank_sorted = sorted(candidates, key=lambda x: (-x["rerank_score"], x["doc_id"]))
        judged_sorted = sorted(candidates, key=lambda x: (-x["judged_relevance"], x["doc_id"]))

        judged_best = judged_sorted[0]
        judged_best_id = judged_best["doc_id"]
        base_rank_map = {c["doc_id"]: i + 1 for i, c in enumerate(base_sorted)}
        rerank_rank_map = {c["doc_id"]: i + 1 for i, c in enumerate(rerank_sorted)}

        base_rank = base_rank_map.get(judged_best_id)
        rerank_rank = rerank_rank_map.get(judged_best_id)
        demoted = (base_rank is not None and rerank_rank is not None and rerank_rank > base_rank)

        top_rerank = rerank_sorted[0]
        judged_best_raw = judged_best["rerank_raw_score"]
        top_rerank_raw = top_rerank["rerank_raw_score"]
        judged_base_values = [c["base_score"] for c in candidates]

        diff_lines: list[str] | None = None
        if demoted and top_rerank["doc_id"] != judged_best_id:
            diff_lines = short_diff(judged_best["content"], top_rerank["content"], max_lines=180)

        top1_rerank_lengths.append(int(top_rerank["chunk_token_length"]))
        top1_judged_lengths.append(int(judged_best["chunk_token_length"]))
        top1_rerank_overlaps.append(float(top_rerank["overlap_with_query_terms"]))
        top1_judged_overlaps.append(float(judged_best["overlap_with_query_terms"]))

        table_rows.append(
            {
                "query_id": qid,
                "query_type": classify_query_type(query),
                "judged_best_doc_id": judged_best_id,
                "base_rank": base_rank,
                "rerank_rank": rerank_rank,
                "rerank_raw_score": judged_best_raw,
                "top_rerank_raw_score": top_rerank_raw,
                "base_percentile": percentile_rank(judged_base_values, judged_best["base_score"]),
                "dense_percentile": judged_best["dense_percentile"],
                "chunk_length": judged_best["chunk_token_length"],
                "file_type": judged_best["file_type"],
                "overlap_with_query_terms": judged_best["overlap_with_query_terms"],
                "demoted_by_rerank": demoted,
            }
        )

        per_query.append(
            {
                "query_id": qid,
                "query": query,
                "query_type": classify_query_type(query),
                "judged_best_doc_id": judged_best_id,
                "base_rank_of_judged_best": base_rank,
                "rerank_rank_of_judged_best": rerank_rank,
                "judged_best_rerank_raw_score": judged_best_raw,
                "top_rerank_doc_id": top_rerank["doc_id"],
                "top_rerank_raw_score": top_rerank_raw,
                "rerank_demoted_judged_best": demoted,
                "top10_base_candidates": [
                    {
                        "rank": i + 1,
                        "doc_id": c["doc_id"],
                        "file": c["file"],
                        "base_score": c["base_score"],
                        "rerank_score": c["rerank_score"],
                        "rerank_raw_score": c["rerank_raw_score"],
                        "judged_relevance": c["judged_relevance"],
                    }
                    for i, c in enumerate(base_sorted[: args.top_k])
                ],
                "top10_rerank_candidates": [
                    {
                        "rank": i + 1,
                        "doc_id": c["doc_id"],
                        "file": c["file"],
                        "base_score": c["base_score"],
                        "rerank_score": c["rerank_score"],
                        "rerank_raw_score": c["rerank_raw_score"],
                        "judged_relevance": c["judged_relevance"],
                    }
                    for i, c in enumerate(rerank_sorted[: args.top_k])
                ],
                "top10_judged_candidates": [
                    {
                        "rank": i + 1,
                        "doc_id": c["doc_id"],
                        "file": c["file"],
                        "judged_relevance": c["judged_relevance"],
                        "base_score": c["base_score"],
                        "rerank_score": c["rerank_score"],
                        "rerank_raw_score": c["rerank_raw_score"],
                    }
                    for i, c in enumerate(judged_sorted[: args.top_k])
                ],
                "full_candidate_rerank_diagnostics": [
                    {
                        "doc_id": c["doc_id"],
                        "file": c["file"],
                        "file_type": c["file_type"],
                        "base_score": c["base_score"],
                        "rerank_score": c["rerank_score"],
                        "rerank_raw_score": c["rerank_raw_score"],
                        "final_score": c["final_score"],
                        "judged_relevance": c["judged_relevance"],
                        "chunk_token_length": c["chunk_token_length"],
                        "pair_token_length_full": c["pair_token_length_full"],
                        "pair_token_length_after_trunc": c["pair_token_length_after_trunc"],
                        "pair_was_truncated": c["pair_was_truncated"],
                        "vector_score": c["vector_score"],
                        "bm25_score": c["bm25_score"],
                        "dense_percentile": c["dense_percentile"],
                        "overlap_with_query_terms": c["overlap_with_query_terms"],
                        "rerank_input_text": c["rerank_input_text"],
                    }
                    for c in candidates
                ],
                "judged_vs_top_rerank_diff": diff_lines,
            }
        )
        print(
            f"[{idx}/{len(query_ids)}] Q{qid} done: judged_best={judged_best_id} base_rank={base_rank} rerank_rank={rerank_rank}",
            flush=True,
        )

    # Aggregates.
    demotions = [r for r in table_rows if r["demoted_by_rerank"]]
    query_types = sorted({r["query_type"] for r in table_rows})
    type_stats: dict[str, Any] = {}
    for t in query_types:
        rows = [r for r in table_rows if r["query_type"] == t]
        type_stats[t] = {
            "count": len(rows),
            "demoted_count": sum(1 for r in rows if r["demoted_by_rerank"]),
            "demoted_pct": (100.0 * sum(1 for r in rows if r["demoted_by_rerank"]) / len(rows)) if rows else 0.0,
            "mean_base_rank_of_judged_best": statistics.mean(
                [r["base_rank"] for r in rows if isinstance(r["base_rank"], int)]
            )
            if rows
            else None,
            "mean_rerank_rank_of_judged_best": statistics.mean(
                [r["rerank_rank"] for r in rows if isinstance(r["rerank_rank"], int)]
            )
            if rows
            else None,
        }

    trunc_flags = [
        c["pair_was_truncated"]
        for q in per_query
        for c in q["full_candidate_rerank_diagnostics"]
    ]
    trunc_rate = (100.0 * sum(1 for x in trunc_flags if x) / len(trunc_flags)) if trunc_flags else 0.0

    aggregate = {
        "query_count": len(per_query),
        "mean_chunk_length_rerank_top1": statistics.mean(top1_rerank_lengths) if top1_rerank_lengths else None,
        "mean_chunk_length_judged_top1": statistics.mean(top1_judged_lengths) if top1_judged_lengths else None,
        "mean_overlap_rerank_top1": statistics.mean(top1_rerank_overlaps) if top1_rerank_overlaps else None,
        "mean_overlap_judged_top1": statistics.mean(top1_judged_overlaps) if top1_judged_overlaps else None,
        "judged_best_demoted_by_rerank_count": len(demotions),
        "judged_best_demoted_by_rerank_pct": (100.0 * len(demotions) / len(table_rows)) if table_rows else 0.0,
        "pair_truncation_rate_pct": trunc_rate,
        "query_type_stats": type_stats,
    }

    result = {
        "config": {
            "labels": str(args.labels),
            "responses": str(args.responses),
            "duckdb_path": str(args.duckdb_path),
            "reranker_model": args.reranker_model,
            "top_k": args.top_k,
        },
        "aggregate": aggregate,
        "per_query_structured_table": table_rows,
        "per_query_diagnostics": per_query,
    }
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = []
    md.append("# Reranker Diagnostic Deep Dive")
    md.append("")
    md.append("## Aggregate")
    md.append(f"- queries: {aggregate['query_count']}")
    md.append(f"- judged best demoted by rerank: {aggregate['judged_best_demoted_by_rerank_pct']:.1f}% ({aggregate['judged_best_demoted_by_rerank_count']}/{aggregate['query_count']})")
    md.append(f"- mean chunk length rerank top-1: {aggregate['mean_chunk_length_rerank_top1']}")
    md.append(f"- mean chunk length judged top-1: {aggregate['mean_chunk_length_judged_top1']}")
    md.append(f"- mean token overlap rerank top-1: {aggregate['mean_overlap_rerank_top1']}")
    md.append(f"- mean token overlap judged top-1: {aggregate['mean_overlap_judged_top1']}")
    md.append(f"- rerank pair truncation rate: {aggregate['pair_truncation_rate_pct']:.1f}%")
    md.append("")
    md.append("## Structured Table")
    md.append("| Query | Type | judged_best_doc_id | base_rank | rerank_rank | rerank_raw_score | base_percentile | dense_percentile | chunk_length | file_type | overlap_with_query_terms | demoted |")
    md.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|")
    for r in table_rows:
        dense = "NA" if r["dense_percentile"] is None else f"{r['dense_percentile']:.4f}"
        basep = "NA" if r["base_percentile"] is None else f"{r['base_percentile']:.4f}"
        md.append(
            f"| {r['query_id']} | {r['query_type']} | {r['judged_best_doc_id']} | {r['base_rank']} | {r['rerank_rank']} | {r['rerank_raw_score']:.6f} | {basep} | {dense} | {r['chunk_length']} | {r['file_type']} | {r['overlap_with_query_terms']:.4f} | {r['demoted_by_rerank']} |"
        )
    md.append("")
    md.append("## Query Type Clustering")
    md.append("| Type | Count | Demoted % | Mean base rank(judged best) | Mean rerank rank(judged best) |")
    md.append("|---|---:|---:|---:|---:|")
    for t, s in type_stats.items():
        md.append(
            f"| {t} | {s['count']} | {s['demoted_pct']:.1f} | {s['mean_base_rank_of_judged_best']} | {s['mean_rerank_rank_of_judged_best']} |"
        )
    md.append("")
    md.append(f"Full per-query top10 lists, raw scores, rerank inputs, token lengths, and diffs are in `{out_json}`.")
    out_md.write_text("\n".join(md), encoding="utf-8")

    print(f"Saved: {out_json}")
    print(f"Saved: {out_md}")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
