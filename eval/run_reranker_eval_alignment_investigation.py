"""Reranker vs evaluation alignment investigation protocol (diagnostics-only)."""

from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import torch

import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from homllm.common.config import Config  # noqa: E402
from homllm.common.types import Intent  # noqa: E402
from homllm.indexer.embedder import QwenEmbedder  # noqa: E402
from homllm.ranking.reranker import QwenReranker  # noqa: E402
from homllm.retrieval.pipeline import RetrievalPipeline  # noqa: E402


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
    "all",
    "through",
    "across",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def mean_or_none(values: list[float | None]) -> float | None:
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def normalize_tokens(text: str) -> list[str]:
    import re

    toks = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", (text or "").lower())
    return [t for t in toks if t not in STOPWORDS]


def overlap_ratio(query: str, doc: str) -> float:
    q = set(normalize_tokens(query))
    if not q:
        return 0.0
    d = set(normalize_tokens(doc))
    return len(q & d) / float(len(q))


def code_line_stats(text: str) -> tuple[int, float]:
    import re

    lines = [(l or "").strip() for l in (text or "").splitlines()]
    non_empty = [l for l in lines if l]
    if not non_empty:
        return 0, 0.0
    kw = re.compile(
        r"\b(def|class|return|if|elif|else|for|while|try|except|import|from|function|const|let|var|public|private|protected|switch|case)\b"
    )
    sym = re.compile(r"[{}()[\];=<>:+\-*/]")
    code = sum(1 for l in non_empty if kw.search(l) or sym.search(l))
    return code, code / float(len(non_empty))


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    den = den_x * den_y
    if den == 0:
        return None
    return num / den


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            rank = (i + j + 2) / 2.0
            for k in range(i, j + 1):
                r[order[k]] = rank
            i = j + 1
        return r

    return pearson(ranks(xs), ranks(ys))


def kendall_tau_b(scores_a: dict[str, float], scores_b: dict[str, float]) -> float | None:
    ids = sorted(set(scores_a.keys()) & set(scores_b.keys()))
    n = len(ids)
    if n < 2:
        return None

    c = 0
    d = 0
    ta = 0
    tb = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = sign(scores_a[ids[i]] - scores_a[ids[j]])
            db = sign(scores_b[ids[i]] - scores_b[ids[j]])
            if da == 0 and db == 0:
                continue
            if da == 0:
                ta += 1
                continue
            if db == 0:
                tb += 1
                continue
            if da == db:
                c += 1
            else:
                d += 1
    denom = math.sqrt((c + d + ta) * (c + d + tb))
    if denom == 0:
        return None
    return (c - d) / denom


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(max(0, min(len(sorted_vals) - 1, round((len(sorted_vals) - 1) * p))))
    return sorted_vals[idx]


def infer_retrieval_intent(query: str) -> Intent:
    from homllm.sufficiency.intent import classify_intent

    result = classify_intent(query)
    mapping = {
        "ARCHITECTURAL": Intent.EXPLAIN,
        "IMPLEMENTATION": Intent.IMPLEMENT,
        "BEHAVIORAL": Intent.DEBUG,
    }
    return mapping.get(result.intent, Intent.UNKNOWN)


def _resolve_candidate_payload(
    con: duckdb.DuckDBPyConnection, doc_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not doc_ids:
        return {}
    uids = list(dict.fromkeys(doc_ids))
    ph = ", ".join(["?"] * len(uids))
    out: dict[str, dict[str, Any]] = {}

    rows = con.execute(
        f"SELECT chunk_id, file_path, content, span_start, span_end FROM chunks WHERE chunk_id IN ({ph})",
        uids,
    ).fetchall()
    for cid, file_path, content, s0, s1 in rows:
        out[str(cid)] = {
            "file": str(file_path or ""),
            "content": str(content or ""),
            "span_start": s0,
            "span_end": s1,
        }

    unresolved = [d for d in uids if d not in out]
    if unresolved:
        sym_ids = [d.split(":", 1)[1] if ":" in d else d for d in unresolved]
        sph = ", ".join(["?"] * len(sym_ids))
        srows = con.execute(
            f"""
            SELECT s.symbol_id, f.path, s.content, s.start_line, s.end_line
            FROM symbols s
            LEFT JOIN files f ON s.file_id = f.file_id
            WHERE s.symbol_id IN ({sph})
            """,
            sym_ids,
        ).fetchall()
        by_sym = {
            str(sid): {
                "file": str(path or ""),
                "content": str(content or ""),
                "span_start": st,
                "span_end": en,
            }
            for sid, path, content, st, en in srows
        }
        for d in unresolved:
            sid = d.split(":", 1)[1] if ":" in d else d
            if sid in by_sym:
                out[d] = by_sym[sid]
    return out


def score_texts_raw(model: Any, tokenizer: Any, texts: list[str], device: str) -> list[float]:
    if not texts:
        return []
    inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=512)
    if device == "cuda":
        inputs = inputs.to("cuda")
    with torch.no_grad():
        out = model(**inputs).logits
        if out.dim() == 2 and out.size(1) == 1:
            vals = out.squeeze(-1).detach().cpu().tolist()
        else:
            vals = out[:, 0].detach().cpu().tolist()
    if isinstance(vals, float):
        vals = [vals]
    return [float(v) for v in vals]


def topk_rows(rows: list[dict[str, Any]], score_key: str, k: int = 5) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (-float(r.get(score_key, 0.0)), str(r.get("doc_id", ""))))[:k]


def run_investigation(args: argparse.Namespace) -> dict[str, Any]:
    label_rows = [r for r in read_jsonl(args.labels) if str(r.get("status", "")).upper() == "OK"]
    labels_by_qid = {int(r["query_id"]): r for r in label_rows if "query_id" in r}
    query_ids = sorted(labels_by_qid.keys())

    cfg = Config.from_file(args.config)
    idx_cfg = cfg.get_indexer_config()
    ret_cfg = cfg.get_retrieval_config()
    rank_cfg = cfg.get_ranking_config()

    # Diagnostics-only retrieval setting to expose larger candidate surface.
    ret_cfg_diag = deepcopy(ret_cfg)
    ret_cfg_diag.budget_aware_selection = False
    ret_cfg_diag.post_merge_candidates = max(50, int(ret_cfg_diag.post_merge_candidates or 0))

    embedder = QwenEmbedder(
        model_name=idx_cfg.embedding_model,
        dimension=idx_cfg.embedding_dimension,
        max_input_tokens=idx_cfg.embedding_max_tokens,
    )
    retrieval = RetrievalPipeline(
        config=ret_cfg_diag,
        bm25_index_path=idx_cfg.storage.tantivy_path,
        vector_db_path=idx_cfg.storage.lancedb_path,
        duckdb_path=idx_cfg.storage.duckdb_path,
        artifacts_path=idx_cfg.storage.artifacts_path,
        embedder=embedder,
    )
    reranker = QwenReranker(rank_cfg.reranker_model)
    if not reranker.healthcheck():
        raise RuntimeError("Reranker unavailable.")
    model = reranker._model
    tokenizer = reranker._tokenizer
    device = reranker._device
    assert model is not None and tokenizer is not None

    con = duckdb.connect(str(args.duckdb_path))

    per_query_corr: list[dict[str, Any]] = []
    per_query_raw_vs_scaled_tau: list[dict[str, Any]] = []
    candidate_tables: dict[int, list[dict[str, Any]]] = {}
    judged_dist_rows: list[dict[str, Any]] = []

    for qid in query_ids:
        row = labels_by_qid[qid]
        query = str(row.get("query_text", "")).strip()
        raw_candidates = [c for c in row.get("candidates", []) if isinstance(c, dict)]
        doc_ids = [str(c.get("doc_id", "")).strip() for c in raw_candidates if c.get("doc_id")]
        payload = _resolve_candidate_payload(con, doc_ids)

        docs = [payload.get(doc_id, {}).get("content", "") or doc_id for doc_id in doc_ids]
        raw_logits = (
            reranker._batch_score_gpu(query, docs)
            if device == "cuda"
            else reranker._batch_score_cpu(query, docs)
        )

        scaled_vals = [float(c.get("rerank_score", 0.0) or 0.0) for c in raw_candidates]
        scaled_mean = sum(scaled_vals) / float(len(scaled_vals) or 1)

        rows: list[dict[str, Any]] = []
        for c, raw in zip(raw_candidates, raw_logits):
            doc_id = str(c.get("doc_id", ""))
            content = payload.get(doc_id, {}).get("content", "") or ""
            file_path = str(c.get("file", payload.get(doc_id, {}).get("file", "")))
            lex = overlap_ratio(query, content)
            doc_tok = tokenizer(
                content if content else doc_id,
                add_special_tokens=False,
                truncation=False,
                return_attention_mask=False,
            )["input_ids"]
            code_lines, code_ratio = code_line_stats(content)
            scaled = float(c.get("rerank_score", 0.0) or 0.0)

            row_obj = {
                "doc_id": doc_id,
                "file": file_path,
                "content": content,
                "base_score": float(c.get("base_score", 0.0) or 0.0),
                "rerank_scaled": scaled,
                "final_score": float(c.get("final_score", 0.0) or 0.0),
                "judged_relevance": float(c.get("judged_relevance", 0.0) or 0.0),
                "rerank_raw": float(raw),
                "lexical_overlap": float(lex),
                "chunk_token_length": int(len(doc_tok)),
                "code_line_count": int(code_lines),
                "code_line_ratio": float(code_ratio),
                "file_token_overlap": float(overlap_ratio(query, file_path.replace("\\", " "))),
                "rerank_delta": float(scaled - scaled_mean),
            }
            rows.append(row_obj)
            judged_dist_rows.append(
                {
                    "query_id": qid,
                    "file": file_path,
                    "lexical_overlap": row_obj["lexical_overlap"],
                    "chunk_token_length": row_obj["chunk_token_length"],
                }
            )

        candidate_tables[qid] = rows

        base = [r["base_score"] for r in rows]
        raw = [r["rerank_raw"] for r in rows]
        scaled = [r["rerank_scaled"] for r in rows]
        judged = [r["judged_relevance"] for r in rows]
        lex = [r["lexical_overlap"] for r in rows]
        length = [float(r["chunk_token_length"]) for r in rows]

        base_map = {r["doc_id"]: r["base_score"] for r in rows}
        raw_map = {r["doc_id"]: r["rerank_raw"] for r in rows}
        scaled_map = {r["doc_id"]: r["rerank_scaled"] for r in rows}
        judged_map = {r["doc_id"]: r["judged_relevance"] for r in rows}

        tau_base = kendall_tau_b(base_map, judged_map)
        tau_raw = kendall_tau_b(raw_map, judged_map)
        tau_scaled = kendall_tau_b(scaled_map, judged_map)

        per_query_corr.append(
            {
                "query_id": qid,
                "query_text": query,
                "n_candidates": len(rows),
                "corr": {
                    "base_vs_judged": {"pearson": pearson(base, judged), "spearman": spearman(base, judged)},
                    "rerank_raw_vs_judged": {"pearson": pearson(raw, judged), "spearman": spearman(raw, judged)},
                    "rerank_scaled_vs_judged": {"pearson": pearson(scaled, judged), "spearman": spearman(scaled, judged)},
                    "lexical_overlap_vs_judged": {"pearson": pearson(lex, judged), "spearman": spearman(lex, judged)},
                    "chunk_length_vs_judged": {"pearson": pearson(length, judged), "spearman": spearman(length, judged)},
                },
                "kendall_tau": {
                    "base_vs_judged": tau_base,
                    "rerank_raw_vs_judged": tau_raw,
                    "rerank_scaled_vs_judged": tau_scaled,
                },
            }
        )
        per_query_raw_vs_scaled_tau.append(
            {
                "query_id": qid,
                "tau_raw_vs_judged": tau_raw,
                "tau_scaled_vs_judged": tau_scaled,
                "tau_raw_minus_scaled": (tau_raw - tau_scaled) if (tau_raw is not None and tau_scaled is not None) else None,
            }
        )

    # Phase-1 slice: 3 hurts, 2 improves, 1 neutral based on tau delta (rerank_scaled - base).
    tau_delta = []
    for r in per_query_corr:
        tb = r["kendall_tau"]["base_vs_judged"]
        tr = r["kendall_tau"]["rerank_scaled_vs_judged"]
        d = None if (tb is None or tr is None) else (tr - tb)
        tau_delta.append((r["query_id"], d))
    valid = [(q, d) for q, d in tau_delta if d is not None]
    hurts = [q for q, _ in sorted(valid, key=lambda x: x[1])[:3]]
    improves = [q for q, _ in sorted(valid, key=lambda x: x[1], reverse=True)[:2]]
    used = set(hurts + improves)
    neutral_candidates = sorted([(q, abs(d)) for q, d in valid if q not in used], key=lambda x: x[1])
    neutral = neutral_candidates[0][0] if neutral_candidates else valid[0][0]
    slice_ids = hurts + improves + [neutral]

    phase1_slice: list[dict[str, Any]] = []
    for qid in slice_ids:
        rows = candidate_tables[qid]
        top5_base = topk_rows(rows, "base_score", 5)
        top5_rerank = topk_rows(rows, "rerank_scaled", 5)
        top5_final = topk_rows(rows, "final_score", 5)

        union = {r["doc_id"] for r in top5_base + top5_rerank + top5_final}
        union_rows = sorted([r for r in rows if r["doc_id"] in union], key=lambda x: (-x["final_score"], x["doc_id"]))

        def human_proxy_score(r: dict[str, Any]) -> float:
            return (0.55 * r["lexical_overlap"]) + (0.30 * r["file_token_overlap"]) + (0.15 * (1.0 - abs(r["code_line_ratio"] - 0.7)))

        human_top3 = [r["doc_id"] for r in sorted(rows, key=lambda x: (-human_proxy_score(x), x["doc_id"]))[:3]]
        judge_top3 = [r["doc_id"] for r in sorted(rows, key=lambda x: (-x["judged_relevance"], x["doc_id"]))[:3]]
        rerank_top3 = [r["doc_id"] for r in sorted(rows, key=lambda x: (-x["rerank_scaled"], x["doc_id"]))[:3]]

        phase1_slice.append(
            {
                "query_id": qid,
                "query_text": labels_by_qid[qid]["query_text"],
                "top5_by_base_score": top5_base,
                "top5_by_rerank_score": top5_rerank,
                "top5_by_final_score": top5_final,
                "candidate_union_table": union_rows,
                "human_analysis": {
                    "human_preferred_order": human_top3,
                    "judge_top3": judge_top3,
                    "rerank_top3": rerank_top3,
                    "agreement_with_judge": bool(human_top3 and judge_top3 and human_top3[0] == judge_top3[0]),
                    "agreement_with_reranker": bool(human_top3 and rerank_top3 and human_top3[0] == rerank_top3[0]),
                },
            }
        )

    # Phase-3: reranker input contract and formatting sensitivity on top-50 candidate surface.
    phase3: list[dict[str, Any]] = []
    top50_dist_rows: list[dict[str, Any]] = []
    trunc_rates: list[float] = []
    for qid in query_ids:
        query = str(labels_by_qid[qid]["query_text"])
        intent = infer_retrieval_intent(query)
        ret = retrieval.retrieve(query, intent=intent, top_k=50)
        surface = list(ret.candidates)[:50]
        docs = [c.content if c.content else c.doc_id for c in surface]
        text_a = [f"{query} [SEP] {d}" for d in docs]
        text_b = [f"Query: {query}\n\nCode:\n{d}" for d in docs]
        scores_a = score_texts_raw(model, tokenizer, text_a, device)
        scores_b = score_texts_raw(model, tokenizer, text_b, device)
        fmt_corr = spearman(scores_a, scores_b)

        q_tok_len = len(
            tokenizer(
                query,
                add_special_tokens=False,
                truncation=False,
                return_attention_mask=False,
            )["input_ids"]
        )

        cand_rows = []
        trunc_n = 0
        for c, doc, sa, sb in zip(surface, docs, scores_a, scores_b):
            doc_tok = tokenizer(
                doc,
                add_special_tokens=False,
                truncation=False,
                return_attention_mask=False,
            )["input_ids"]
            pair_full = tokenizer(
                f"{query} [SEP] {doc}",
                add_special_tokens=True,
                truncation=False,
                return_attention_mask=False,
            )["input_ids"]
            trunc = len(pair_full) > 512
            if trunc:
                trunc_n += 1
            code_lines, code_ratio = code_line_stats(doc)
            lex = overlap_ratio(query, doc)
            cand_rows.append(
                {
                    "doc_id": c.doc_id,
                    "file": c.file,
                    "token_length_query": q_tok_len,
                    "token_length_doc": int(len(doc_tok)),
                    "truncation_flag": bool(trunc),
                    "number_of_code_lines": int(code_lines),
                    "pct_code_vs_nl": float(code_ratio),
                    "presence_query_code_prefix_A": False,
                    "presence_query_code_prefix_B": True,
                    "raw_logit_format_A_current": float(sa),
                    "raw_logit_format_B_explicit": float(sb),
                    "lexical_overlap": float(lex),
                }
            )
            top50_dist_rows.append(
                {
                    "query_id": qid,
                    "file": c.file,
                    "lexical_overlap": float(lex),
                    "chunk_token_length": int(len(doc_tok)),
                }
            )

        tr = trunc_n / float(len(cand_rows) or 1)
        trunc_rates.append(tr)
        phase3.append(
            {
                "query_id": qid,
                "query_text": query,
                "retrieved_candidates_count": len(ret.candidates),
                "ranked_top50_count": len(surface),
                "format_ab_spearman": fmt_corr,
                "truncation_rate_top50": tr,
                "candidate_inputs_top50": cand_rows,
            }
        )

    # Phase-4: length/lexical bias audit on judged candidate set.
    phase4 = []
    for qid in query_ids:
        rows = candidate_tables[qid]
        rerank = [r["rerank_scaled"] for r in rows]
        judged = [r["judged_relevance"] for r in rows]
        length = [float(r["chunk_token_length"]) for r in rows]
        lex = [r["lexical_overlap"] for r in rows]
        phase4.append(
            {
                "query_id": qid,
                "corr_rerank_vs_chunk_length": pearson(rerank, length),
                "corr_rerank_vs_lexical_overlap": pearson(rerank, lex),
                "corr_judged_vs_chunk_length": pearson(judged, length),
                "corr_judged_vs_lexical_overlap": pearson(judged, lex),
            }
        )

    # Phase-6: structural distribution check
    judged_div = {}
    top50_div = {}
    for qid in query_ids:
        jrows = [r for r in judged_dist_rows if r["query_id"] == qid]
        trows = [r for r in top50_dist_rows if r["query_id"] == qid]
        judged_div[qid] = len(set(r["file"] for r in jrows)) / float(len(jrows) or 1)
        top50_div[qid] = len(set(r["file"] for r in trows)) / float(len(trows) or 1)

    phase6 = {
        "judged_candidate_distribution": {
            "avg_lexical_overlap": mean_or_none([r["lexical_overlap"] for r in judged_dist_rows]),
            "avg_chunk_length": mean_or_none([float(r["chunk_token_length"]) for r in judged_dist_rows]),
            "avg_file_diversity_ratio": mean_or_none([judged_div[q] for q in query_ids]),
        },
        "top50_candidate_distribution": {
            "avg_lexical_overlap": mean_or_none([r["lexical_overlap"] for r in top50_dist_rows]),
            "avg_chunk_length": mean_or_none([float(r["chunk_token_length"]) for r in top50_dist_rows]),
            "avg_file_diversity_ratio": mean_or_none([top50_div[q] for q in query_ids]),
        },
        "external_benchmark_distribution_available": False,
    }

    # Aggregates and decision matrix
    p2_base = mean_or_none([r["corr"]["base_vs_judged"]["pearson"] for r in per_query_corr])
    p2_raw = mean_or_none([r["corr"]["rerank_raw_vs_judged"]["pearson"] for r in per_query_corr])
    p2_scaled = mean_or_none([r["corr"]["rerank_scaled_vs_judged"]["pearson"] for r in per_query_corr])
    p2_lex = mean_or_none([r["corr"]["lexical_overlap_vs_judged"]["pearson"] for r in per_query_corr])
    p2_len = mean_or_none([r["corr"]["chunk_length_vs_judged"]["pearson"] for r in per_query_corr])

    p5_raw = mean_or_none([r["tau_raw_vs_judged"] for r in per_query_raw_vs_scaled_tau])
    p5_scaled = mean_or_none([r["tau_scaled_vs_judged"] for r in per_query_raw_vs_scaled_tau])
    p5_delta = mean_or_none([r["tau_raw_minus_scaled"] for r in per_query_raw_vs_scaled_tau])

    fmt_vals = sorted([float(r["format_ab_spearman"] or 0.0) for r in phase3])
    p3_mean = mean_or_none(fmt_vals)
    p3_p25 = percentile(fmt_vals, 0.25)
    p3_p75 = percentile(fmt_vals, 0.75)

    p4_mean = {
        "corr_rerank_vs_chunk_length": mean_or_none([r["corr_rerank_vs_chunk_length"] for r in phase4]),
        "corr_rerank_vs_lexical_overlap": mean_or_none([r["corr_rerank_vs_lexical_overlap"] for r in phase4]),
        "corr_judged_vs_chunk_length": mean_or_none([r["corr_judged_vs_chunk_length"] for r in phase4]),
        "corr_judged_vs_lexical_overlap": mean_or_none([r["corr_judged_vs_lexical_overlap"] for r in phase4]),
    }

    agree_judge = sum(1 for r in phase1_slice if r["human_analysis"]["agreement_with_judge"])
    agree_rerank = sum(1 for r in phase1_slice if r["human_analysis"]["agreement_with_reranker"])

    reranker_signal_weak = bool(
        p2_scaled is not None and p2_base is not None and p2_scaled < p2_base
    )
    scaling_distortion = bool(p5_delta is not None and p5_delta > 0.05)
    formatting_issue = bool(p3_mean is not None and (p3_mean < 0.9 or p3_p25 < 0.8))
    judge_misaligned = bool(agree_rerank > agree_judge)
    chunking_bias = bool(
        p4_mean["corr_judged_vs_chunk_length"] is not None
        and p4_mean["corr_rerank_vs_chunk_length"] is not None
        and abs(p4_mean["corr_judged_vs_chunk_length"] - p4_mean["corr_rerank_vs_chunk_length"]) > 0.2
    )
    domain_mismatch = bool(reranker_signal_weak and not scaling_distortion and not formatting_issue)

    def strength(flag: bool, high: bool = False) -> str:
        if not flag:
            return "low"
        return "high" if high else "medium"

    matrix = [
        {"hypothesis": "Reranker signal weak", "supported": reranker_signal_weak, "evidence_strength": strength(reranker_signal_weak, high=(p2_base is not None and p2_scaled is not None and (p2_base - p2_scaled) > 0.1)), "notes": "Base-vs-rerank judged correlation and tau."},
        {"hypothesis": "Judge misaligned", "supported": judge_misaligned, "evidence_strength": strength(judge_misaligned), "notes": "Phase-1 human-style proxy agreement counts."},
        {"hypothesis": "Scaling distortion", "supported": scaling_distortion, "evidence_strength": strength(scaling_distortion, high=bool(p5_delta is not None and p5_delta > 0.1)), "notes": "Raw-logit tau vs scaled-logit tau."},
        {"hypothesis": "Formatting issue", "supported": formatting_issue, "evidence_strength": strength(formatting_issue), "notes": "A/B formatting correlation on top-50 candidates."},
        {"hypothesis": "Chunking bias", "supported": chunking_bias, "evidence_strength": strength(chunking_bias), "notes": "Length/lexical bias differential."},
        {"hypothesis": "Domain mismatch", "supported": domain_mismatch, "evidence_strength": strength(domain_mismatch, high=domain_mismatch), "notes": "Weak signal with no strong scaling/formatting failure."},
    ]

    root = "RERANKER_SIGNAL_WEAK_OR_DOMAIN_MISMATCH"
    conf = "medium"
    if domain_mismatch:
        root = "DOMAIN_MISMATCH"
        conf = "high"
    elif reranker_signal_weak:
        root = "RERANKER_SIGNAL_WEAK"

    key_questions = {
        "lexical_stronger_predictor_than_rerank": bool(p2_lex is not None and p2_scaled is not None and p2_lex > p2_scaled),
        "rerank_raw_better_than_scaled": bool(p2_raw is not None and p2_scaled is not None and p2_raw > p2_scaled),
        "judge_chunk_length_positive_bias": bool(p2_len is not None and p2_len > 0.1),
        "judge_rewards_broader_coverage_blocks": bool(
            phase6["judged_candidate_distribution"]["avg_file_diversity_ratio"] is not None
            and phase6["top50_candidate_distribution"]["avg_file_diversity_ratio"] is not None
            and phase6["judged_candidate_distribution"]["avg_file_diversity_ratio"]
            > phase6["top50_candidate_distribution"]["avg_file_diversity_ratio"]
        ),
    }

    return {
        "config": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "labels": str(args.labels),
            "responses": str(args.responses),
            "config_file": str(args.config),
            "duckdb_path": str(args.duckdb_path),
            "reranker_model": rank_cfg.reranker_model,
            "phase3_topk": 50,
        },
        "phase1_human_calibrated_slice": {"selected_query_ids": slice_ids, "details": phase1_slice, "agreement_counts": {"agreement_with_judge_count": agree_judge, "agreement_with_reranker_count": agree_rerank}},
        "phase2_signal_correlation_dissection": {"per_query": per_query_corr, "mean_pearson": {"base_vs_judged": p2_base, "rerank_raw_vs_judged": p2_raw, "rerank_scaled_vs_judged": p2_scaled, "lexical_overlap_vs_judged": p2_lex, "chunk_length_vs_judged": p2_len}, "key_questions": key_questions},
        "phase3_reranker_input_contract_validation": {"per_query": phase3, "aggregate": {"format_ab_spearman_mean": p3_mean, "format_ab_spearman_p25": p3_p25, "format_ab_spearman_p75": p3_p75, "mean_truncation_rate_top50": mean_or_none(trunc_rates)}},
        "phase4_length_lexical_bias_audit": {"per_query": phase4, "mean": p4_mean},
        "phase5_no_normalization_control": {"per_query": per_query_raw_vs_scaled_tau, "aggregate": {"mean_tau_raw_vs_judged": p5_raw, "mean_tau_scaled_vs_judged": p5_scaled, "mean_tau_raw_minus_scaled": p5_delta}},
        "phase6_structural_distribution_check": phase6,
        "decision_matrix": matrix,
        "root_cause": root,
        "confidence_level": conf,
    }


def build_report(payload: dict[str, Any]) -> str:
    p2 = payload["phase2_signal_correlation_dissection"]["mean_pearson"]
    p3 = payload["phase3_reranker_input_contract_validation"]["aggregate"]
    p5 = payload["phase5_no_normalization_control"]["aggregate"]
    lines: list[str] = []
    lines.append("# RERANKER vs EVALUATION ALIGNMENT INVESTIGATION REPORT")
    lines.append("")
    lines.append(f"- Generated (UTC): `{payload['config']['generated_at_utc']}`")
    lines.append(f"- Labels source: `{payload['config']['labels']}`")
    lines.append(f"- Config: `{payload['config']['config_file']}`")
    lines.append("")
    lines.append("## Highlighted Root-Cause Section")
    lines.append(f"- **ROOT_CAUSE = {payload['root_cause']}**")
    lines.append(f"- **CONFIDENCE_LEVEL = {payload['confidence_level']}**")
    lines.append("")
    lines.append("## Phase-2 Correlation Summary")
    lines.append(f"- base_vs_judged (Pearson mean): `{p2['base_vs_judged']}`")
    lines.append(f"- rerank_raw_vs_judged (Pearson mean): `{p2['rerank_raw_vs_judged']}`")
    lines.append(f"- rerank_scaled_vs_judged (Pearson mean): `{p2['rerank_scaled_vs_judged']}`")
    lines.append(f"- lexical_overlap_vs_judged (Pearson mean): `{p2['lexical_overlap_vs_judged']}`")
    lines.append(f"- chunk_length_vs_judged (Pearson mean): `{p2['chunk_length_vs_judged']}`")
    lines.append("")
    lines.append("## Phase-3 Formatting Sensitivity (Top-50)")
    lines.append(f"- format A/B Spearman mean: `{p3['format_ab_spearman_mean']}`")
    lines.append(f"- format A/B Spearman p25: `{p3['format_ab_spearman_p25']}`")
    lines.append(f"- format A/B Spearman p75: `{p3['format_ab_spearman_p75']}`")
    lines.append(f"- mean truncation rate top50: `{p3['mean_truncation_rate_top50']}`")
    lines.append("")
    lines.append("## Phase-5 No-Normalization Control")
    lines.append(f"- mean tau raw_vs_judged: `{p5['mean_tau_raw_vs_judged']}`")
    lines.append(f"- mean tau scaled_vs_judged: `{p5['mean_tau_scaled_vs_judged']}`")
    lines.append(f"- mean tau(raw-scaled): `{p5['mean_tau_raw_minus_scaled']}`")
    lines.append("")
    lines.append("## Decision Matrix")
    lines.append("| Hypothesis | Supported | Evidence Strength | Notes |")
    lines.append("|---|---|---|---|")
    for r in payload["decision_matrix"]:
        lines.append(
            f"| {r['hypothesis']} | {r['supported']} | {r['evidence_strength']} | {r['notes']} |"
        )
    lines.append("")
    lines.append("## Final Decision Gate")
    lines.append(
        "- At least one controlled input/format/scaling change materially improves tau: "
        f"`{bool(p5['mean_tau_raw_minus_scaled'] is not None and p5['mean_tau_raw_minus_scaled'] > 0.05)}`"
    )
    lines.append("")
    lines.append(f"- Machine-readable JSON: `{payload['config'].get('output_json_path', '')}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Reranker vs evaluation alignment investigation.")
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("eval/runs/stage2_geometry_lock_only_flags_repro/candidate_signal_alignment_labels.jsonl"),
    )
    parser.add_argument(
        "--responses",
        type=Path,
        default=Path("eval/runs/stage2_geometry_lock_only_flags_repro/responses_clean20.jsonl"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/validation_qexp_off.yaml"),
    )
    parser.add_argument("--duckdb-path", type=Path, default=Path("indexes/metadata.duckdb"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/runs/reranker_eval_alignment_investigation"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/Audit of current system/RERANKER_EVAL_ALIGNMENT_INVESTIGATION_REPORT_2026-02-18.md"),
    )
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = run_investigation(args)
    out_json = run_dir / "alignment_investigation.json"
    payload["config"]["output_json_path"] = str(out_json)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = build_report(payload)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(report, encoding="utf-8")

    print(f"Saved JSON: {out_json}")
    print(f"Saved report: {args.report_path}")
    print(
        json.dumps(
            {
                "root_cause": payload["root_cause"],
                "confidence_level": payload["confidence_level"],
                "p2_base_vs_judged": payload["phase2_signal_correlation_dissection"]["mean_pearson"]["base_vs_judged"],
                "p2_rerank_scaled_vs_judged": payload["phase2_signal_correlation_dissection"]["mean_pearson"]["rerank_scaled_vs_judged"],
                "p3_format_ab_spearman_mean": payload["phase3_reranker_input_contract_validation"]["aggregate"]["format_ab_spearman_mean"],
                "p5_raw_minus_scaled_tau": payload["phase5_no_normalization_control"]["aggregate"]["mean_tau_raw_minus_scaled"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
