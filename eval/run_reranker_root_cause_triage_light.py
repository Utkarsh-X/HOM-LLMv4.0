"""Lightweight reranker root-cause triage on 6 probe queries.

Rules honored:
- No ranking architecture/scoring geometry changes
- No selector/retrieval logic modifications
- No full BASE20 sweep
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import torch

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_judge import RateLimiter, call_judge, ensure_client, load_judge_config  # noqa: E402
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
    "all",
    "through",
    "across",
}


@dataclass
class ProbeCandidate:
    doc_id: str
    file: str
    content: str
    retrieval_rank: int
    bm25_score: float
    vector_score: float
    hybrid_score: float


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def mean_or_none(vals: list[float | None]) -> float | None:
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return None
    return float(sum(nums) / len(nums))


def normalize_tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", (text or "").lower())
    return [t for t in toks if t not in STOPWORDS]


def overlap_ratio(query: str, text: str) -> float:
    q = set(normalize_tokens(query))
    if not q:
        return 0.0
    t = set(normalize_tokens(text))
    return len(q & t) / float(len(q))


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


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


def precision_at_k(pred_scores: dict[str, float], gold_scores: dict[str, float], k: int) -> float:
    pred = [d for d, _ in sorted(pred_scores.items(), key=lambda kv: (-kv[1], kv[0]))][:k]
    gold = {d for d, _ in sorted(gold_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]}
    if not pred or k <= 0:
        return 0.0
    return len([d for d in pred if d in gold]) / float(k)


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


def build_probe_set(alignment_json: Path) -> dict[str, list[int]]:
    o = json.loads(alignment_json.read_text(encoding="utf-8"))
    rows = []
    for r in o["phase2_signal_correlation_dissection"]["per_query"]:
        qid = int(r["query_id"])
        tb = r["kendall_tau"]["base_vs_judged"]
        tr = r["kendall_tau"]["rerank_scaled_vs_judged"]
        d = None if (tb is None or tr is None) else (tr - tb)
        rows.append((qid, d, tb, tr))

    valid = [r for r in rows if r[1] is not None]
    by_delta = sorted(valid, key=lambda x: x[1])
    hurt = [qid for qid, _, _, _ in by_delta[:2]]

    # helped slightly: prefer non-negative; if insufficient, use closest-to-zero negatives.
    non_negative = [r for r in valid if r[1] >= 0]
    helped = [qid for qid, _, _, _ in sorted(non_negative, key=lambda x: x[1])[:2]]
    if len(helped) < 2:
        remaining = [r for r in sorted(valid, key=lambda x: abs(x[1])) if r[0] not in set(hurt + helped)]
        helped.extend([qid for qid, _, _, _ in remaining[: 2 - len(helped)]])

    used = set(hurt + helped)
    neutral = [qid for qid, _, _, _ in sorted(valid, key=lambda x: abs(x[1])) if qid not in used][:2]

    return {"hurt": hurt, "helped_slightly": helped, "neutral_mixed": neutral}


def build_prompt(query: str, candidates: list[ProbeCandidate], content_chars: int) -> list[dict[str, str]]:
    system_msg = (
        "You are grading candidate code snippets for query relevance.\n"
        "Return ONLY valid JSON.\n"
        "Score each candidate independently on relevance to the query:\n"
        "0 = irrelevant, 10 = directly answers the query with high evidence.\n"
        "Do not use ties unless evidence is truly equal.\n"
    )
    lines: list[str] = []
    lines.append("QUERY:")
    lines.append(query.strip())
    lines.append("")
    lines.append("CANDIDATES:")
    for idx, c in enumerate(candidates, start=1):
        excerpt = (c.content or "").strip()
        if len(excerpt) > content_chars:
            excerpt = excerpt[:content_chars] + "..."
        lines.append(f"[{idx}] doc_id={c.doc_id}")
        lines.append(f"file={c.file}")
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
    return [{"role": "system", "content": system_msg}, {"role": "user", "content": "\n".join(lines)}]


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
            try:
                rel = float(item.get("relevance", 0.0))
            except Exception:
                continue
            scores[doc_id] = max(0.0, min(10.0, rel))
            rat = str(item.get("rationale", "")).strip()
            if rat:
                rationales[doc_id] = rat
    for doc_id in expected_doc_ids:
        if doc_id not in scores:
            scores[doc_id] = 0.0
    return scores, rationales


def _line_overlap_score(query: str, line: str) -> float:
    return overlap_ratio(query, line)


def focused_variant(query: str, content: str, tokenizer: Any, max_tokens: int = 200) -> str:
    lines = (content or "").splitlines()
    if not lines:
        return content or ""
    best_idx = max(range(len(lines)), key=lambda i: _line_overlap_score(query, lines[i]))

    def_re = re.compile(r"^\s*(def|class)\s+\w+")
    start = None
    for i in range(best_idx, -1, -1):
        if def_re.match(lines[i]):
            start = i
            break
    if start is None:
        start = max(0, best_idx - 30)

    base_indent = len(lines[start]) - len(lines[start].lstrip(" "))
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if def_re.match(line) and indent <= base_indent:
            end = j
            break
    block = "\n".join(lines[start:end]).strip()
    if not block:
        block = "\n".join(lines[max(0, best_idx - 30) : min(len(lines), best_idx + 30)])

    ids = tokenizer(block, add_special_tokens=False, truncation=False, return_attention_mask=False)["input_ids"]
    if len(ids) <= max_tokens:
        return block
    return tokenizer.decode(ids[:max_tokens], skip_special_tokens=True)


def minimal_slice_variant(query: str, content: str, tokenizer: Any, min_lines: int = 40, max_lines: int = 80) -> str:
    lines = (content or "").splitlines()
    if not lines:
        return content or ""
    best_idx = max(range(len(lines)), key=lambda i: _line_overlap_score(query, lines[i]))
    win = max(min_lines, min(max_lines, 60))
    half = win // 2
    s = max(0, best_idx - half)
    e = min(len(lines), s + win)
    s = max(0, e - win)
    return "\n".join(lines[s:e]).strip()


def minmax(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi <= lo:
        return [0.5] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def score_variant(
    reranker: QwenReranker, query: str, docs: list[str], mode: str
) -> list[float]:
    model = reranker._model
    tokenizer = reranker._tokenizer
    device = reranker._device
    if model is None or tokenizer is None:
        return [0.0] * len(docs)

    if mode == "f1":
        pairs = [f"{query} [SEP] {d}" for d in docs]
    elif mode == "f2":
        pairs = [f"Query:\n{query}\n\nCode:\n{d}" for d in docs]
    elif mode == "f3":
        pairs = [f"<query>\n{query}\n</query>\n<code>\n{d}\n</code>" for d in docs]
    else:
        raise ValueError(f"Unknown format mode: {mode}")

    inputs = tokenizer(
        pairs,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    )
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


def metrics_vs_judged(doc_ids: list[str], pred_scores: list[float], judged_map: dict[str, float]) -> dict[str, Any]:
    pred_map = {d: float(s) for d, s in zip(doc_ids, pred_scores)}
    tau = kendall_tau_b(pred_map, judged_map)
    p1 = precision_at_k(pred_map, judged_map, 1)
    p3 = precision_at_k(pred_map, judged_map, 3)
    return {"kendall_tau": tau, "p_at_1": p1, "p_at_3": p3}


def quick_reason(
    query: str,
    base_top1: dict[str, Any],
    rerank_top1: dict[str, Any],
    judged_best: dict[str, Any],
) -> str:
    lines = []
    lines.append(f"Query focus: {query[:120]}")
    lines.append(
        f"Reranker likely favored `{rerank_top1['doc_id']}` due to lexical/structural cues in `{rerank_top1['file']}`."
    )
    lines.append(
        f"Base top-1 was `{base_top1['doc_id']}` from `{base_top1['file']}`, prioritized by retrieval hybrid score."
    )
    lines.append(
        f"Judged-best is `{judged_best['doc_id']}` with judged relevance {judged_best['judged_relevance']}."
    )
    lines.append(
        "Mismatch suggests reranker is weighting cues differently than judged answer-utility criteria."
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    probe = build_probe_set(args.alignment_json)
    selected = probe["hurt"] + probe["helped_slightly"] + probe["neutral_mixed"]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    responses = read_jsonl(args.responses)
    responses_by_qid = {int(r["query_id"]): r for r in responses if "query_id" in r}
    missing = [q for q in selected if q not in responses_by_qid]
    if missing:
        raise RuntimeError(f"Probe query IDs missing in responses: {missing}")

    reranker = QwenReranker(args.reranker_model)
    if not reranker.healthcheck():
        raise RuntimeError("Reranker unavailable.")
    tokenizer = reranker._tokenizer
    if tokenizer is None:
        raise RuntimeError("Tokenizer unavailable.")

    con = duckdb.connect(str(args.duckdb_path))

    # Build probe retrieval-top20 candidates and judge labels (query-level).
    judge_cfg = None
    judge_client = None
    limiter = None
    judge_enabled = not args.skip_judge

    labels_jsonl = args.output_dir / "probe_labels.jsonl"
    existing = {}
    if args.resume and labels_jsonl.exists():
        for r in read_jsonl(labels_jsonl):
            if "query_id" in r:
                existing[int(r["query_id"])] = r

    seed_labels: dict[int, dict[str, Any]] = {}
    if args.seed_labels and args.seed_labels.exists():
        for r in read_jsonl(args.seed_labels):
            if "query_id" not in r:
                continue
            qid = int(r["query_id"])
            cands = [c for c in r.get("candidates", []) if isinstance(c, dict)]
            seed_labels[qid] = {
                "scores": {
                    str(c.get("doc_id", "")): float(c.get("judged_relevance", 0.0) or 0.0)
                    for c in cands
                    if c.get("doc_id")
                },
                "rationales": {
                    str(c.get("doc_id", "")): str(c.get("rationale", "") or "")
                    for c in cands
                    if c.get("doc_id")
                },
            }

    probe_data: dict[int, dict[str, Any]] = {}
    label_rows: list[dict[str, Any]] = []

    for qid in selected:
        resp = responses_by_qid[qid]
        query = str(resp.get("query_text", "")).strip()
        run_id = str(resp.get("run_id", "")).strip()
        diag_path = Path("artifacts") / "runs" / run_id / "candidate_diagnostics.json"
        diag = json.loads(diag_path.read_text(encoding="utf-8"))
        retrieval_top20 = [r for r in (diag.get("retrieval_top20") or []) if isinstance(r, dict)][:20]
        doc_ids = [str(r.get("doc_id", "")) for r in retrieval_top20 if r.get("doc_id")]
        payload = _resolve_candidate_payload(con, doc_ids)

        candidates: list[ProbeCandidate] = []
        for i, r in enumerate(retrieval_top20, start=1):
            doc_id = str(r.get("doc_id", ""))
            if not doc_id:
                continue
            p = payload.get(doc_id, {})
            candidates.append(
                ProbeCandidate(
                    doc_id=doc_id,
                    file=str(r.get("file", p.get("file", ""))),
                    content=str(p.get("content", "") or ""),
                    retrieval_rank=i,
                    bm25_score=float(r.get("bm25_score", 0.0) or 0.0),
                    vector_score=float(r.get("vector_score", 0.0) or 0.0),
                    hybrid_score=float(r.get("hybrid_score", 0.0) or 0.0),
                )
            )

        doc_set = {c.doc_id for c in candidates}
        label_source = "none"
        judged_scores: dict[str, float] = {}
        judged_rationales: dict[str, str] = {}

        if qid in existing and str(existing[qid].get("status", "")).upper() == "OK":
            ex_scores = {
                str(c["doc_id"]): float(c.get("judged_relevance", 0.0) or 0.0)
                for c in existing[qid].get("candidates", [])
                if isinstance(c, dict)
            }
            ex_rationales = {
                str(c["doc_id"]): str(c.get("rationale", "") or "")
                for c in existing[qid].get("candidates", [])
                if isinstance(c, dict)
            }
            if doc_set.issubset(set(ex_scores.keys())):
                judged_scores = ex_scores
                judged_rationales = ex_rationales
                label_source = "existing_cache"

        if label_source == "none" and qid in seed_labels:
            seed = seed_labels[qid]
            sd_scores = seed["scores"]
            sd_rat = seed["rationales"]
            if doc_set.issubset(set(sd_scores.keys())):
                judged_scores = dict(sd_scores)
                judged_rationales = dict(sd_rat)
                label_source = "seed_labels_full"
            elif args.accept_partial_seed:
                judged_scores = dict(sd_scores)
                judged_rationales = dict(sd_rat)
                label_source = "seed_labels_partial"

        if label_source == "none":
            if not judge_enabled:
                raise RuntimeError(
                    f"Missing judged labels for query {qid} and --skip-judge enabled."
                )
            if judge_cfg is None:
                judge_cfg = load_judge_config(args.judge_config, provider_override=args.provider)
                if args.rpm is not None:
                    judge_cfg.requests_per_minute = int(args.rpm)
                judge_client = ensure_client(judge_cfg)
                limiter = RateLimiter(requests_per_minute=judge_cfg.requests_per_minute)
            messages = build_prompt(query, candidates, content_chars=args.content_chars)
            assert limiter is not None and judge_client is not None and judge_cfg is not None
            limiter.acquire()
            judged_raw, model_used = call_judge(judge_client, judge_cfg, messages)
            judged_scores, judged_rationales = parse_labels(
                judged_raw, [c.doc_id for c in candidates]
            )
            rec = {
                "query_id": qid,
                "query_text": query,
                "run_id": run_id,
                "status": "OK",
                "judge_provider": judge_cfg.provider,
                "judge_model_config": judge_cfg.model,
                "judge_model_used": model_used,
                "candidates": [
                    {
                        "doc_id": c.doc_id,
                        "file": c.file,
                        "judged_relevance": judged_scores.get(c.doc_id, 0.0),
                        "rationale": judged_rationales.get(c.doc_id, ""),
                    }
                    for c in candidates
                ],
            }
            label_rows.append(rec)
            label_source = "live_judge"

        for c in candidates:
            if c.doc_id not in judged_scores:
                judged_scores[c.doc_id] = 0.0

        probe_data[qid] = {
            "query": query,
            "run_id": run_id,
            "candidates": candidates,
            "judged_scores": judged_scores,
            "judged_rationales": judged_rationales,
            "label_source": label_source,
        }

    if label_rows:
        all_rows = list(existing.values()) + label_rows
        all_rows = sorted(all_rows, key=lambda r: int(r.get("query_id", 0)))
        labels_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with labels_jsonl.open("w", encoding="utf-8") as f:
            for r in all_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Phase 1 + 2 + 3 per-query runs.
    phase1_rows: list[dict[str, Any]] = []
    phase2_rows: list[dict[str, Any]] = []
    phase3_rows: list[dict[str, Any]] = []
    compact_rows: list[dict[str, Any]] = []
    qualitative_rows: list[dict[str, Any]] = []

    for qid in selected:
        q = probe_data[qid]["query"]
        cands: list[ProbeCandidate] = probe_data[qid]["candidates"]
        judged_map: dict[str, float] = probe_data[qid]["judged_scores"]
        doc_ids = [c.doc_id for c in cands]

        docs_a = [c.content for c in cands]
        docs_b = [focused_variant(q, c.content, tokenizer, max_tokens=200) for c in cands]
        docs_c = [minimal_slice_variant(q, c.content, tokenizer, min_lines=40, max_lines=80) for c in cands]

        # Phase 1 variants with current format.
        raw_a = score_variant(reranker, q, docs_a, mode="f1")
        raw_b = score_variant(reranker, q, docs_b, mode="f1")
        raw_c = score_variant(reranker, q, docs_c, mode="f1")
        scaled_a = minmax(raw_a)
        scaled_b = minmax(raw_b)
        scaled_c = minmax(raw_c)

        m_a = metrics_vs_judged(doc_ids, raw_a, judged_map)
        m_b = metrics_vs_judged(doc_ids, raw_b, judged_map)
        m_c = metrics_vs_judged(doc_ids, raw_c, judged_map)

        variant_table = []
        for c, sa, sb, sc, ra, rb, rc in zip(cands, scaled_a, scaled_b, scaled_c, raw_a, raw_b, raw_c):
            variant_table.append(
                {
                    "doc_id": c.doc_id,
                    "file": c.file,
                    "chunk_length_tokens_A": len(
                        tokenizer(
                            c.content,
                            add_special_tokens=False,
                            truncation=False,
                            return_attention_mask=False,
                        )["input_ids"]
                    ),
                    "lexical_overlap": overlap_ratio(q, c.content),
                    "base_score": c.hybrid_score,
                    "rerank_raw_A": float(ra),
                    "rerank_scaled_A": float(sa),
                    "rerank_raw_B": float(rb),
                    "rerank_scaled_B": float(sb),
                    "rerank_raw_C": float(rc),
                    "rerank_scaled_C": float(sc),
                    "rerank_delta_A": float(sa - (sum(scaled_a) / float(len(scaled_a) or 1))),
                    "judged_relevance": judged_map.get(c.doc_id, 0.0),
                }
            )

        phase1_rows.append(
            {
                "query_id": qid,
                "query_text": q,
                "metrics": {"A_original": m_a, "B_focused": m_b, "C_minimal_slice": m_c},
                "candidate_table": variant_table,
            }
        )

        compact_rows.append(
            {
                "query_id": qid,
                "group": (
                    "hurt" if qid in probe["hurt"] else
                    "helped_slightly" if qid in probe["helped_slightly"] else
                    "neutral_mixed"
                ),
                "label_source": probe_data[qid]["label_source"],
                "tau_A": m_a["kendall_tau"],
                "tau_B": m_b["kendall_tau"],
                "tau_C": m_c["kendall_tau"],
                "delta_B_minus_A": None if (m_b["kendall_tau"] is None or m_a["kendall_tau"] is None) else (m_b["kendall_tau"] - m_a["kendall_tau"]),
                "delta_C_minus_A": None if (m_c["kendall_tau"] is None or m_a["kendall_tau"] is None) else (m_c["kendall_tau"] - m_a["kendall_tau"]),
                "p1_A": m_a["p_at_1"],
                "p1_B": m_b["p_at_1"],
                "p1_C": m_c["p_at_1"],
                "p3_A": m_a["p_at_3"],
                "p3_B": m_b["p_at_3"],
                "p3_C": m_c["p_at_3"],
            }
        )

        # Phase 2 formatting sensitivity on original chunk A.
        f1 = raw_a
        f2 = score_variant(reranker, q, docs_a, mode="f2")
        f3 = score_variant(reranker, q, docs_a, mode="f3")
        mf1 = metrics_vs_judged(doc_ids, f1, judged_map)
        mf2 = metrics_vs_judged(doc_ids, f2, judged_map)
        mf3 = metrics_vs_judged(doc_ids, f3, judged_map)
        phase2_rows.append(
            {
                "query_id": qid,
                "query_text": q,
                "metrics": {
                    "format1_current": mf1,
                    "format2_query_code": mf2,
                    "format3_xmlish": mf3,
                },
                "cross_format_spearman": {
                    "f1_vs_f2": spearman(f1, f2),
                    "f1_vs_f3": spearman(f1, f3),
                    "f2_vs_f3": spearman(f2, f3),
                },
            }
        )

        # Phase 3 length/lexical bias on original top20 base candidates.
        lengths = []
        lexes = []
        judgeds = []
        reranks = []
        for c, r in zip(cands, raw_a):
            tok_len = len(
                tokenizer(
                    c.content,
                    add_special_tokens=False,
                    truncation=False,
                    return_attention_mask=False,
                )["input_ids"]
            )
            lengths.append(float(tok_len))
            lex = overlap_ratio(q, c.content)
            lexes.append(lex)
            judgeds.append(float(judged_map.get(c.doc_id, 0.0)))
            reranks.append(float(r))
        phase3_rows.append(
            {
                "query_id": qid,
                "query_text": q,
                "corr_length_vs_judged": pearson(lengths, judgeds),
                "corr_lexical_vs_judged": pearson(lexes, judgeds),
                "corr_rerank_vs_judged": pearson(reranks, judgeds),
                "p_at_1_long_chunk_A": m_a["p_at_1"],
                "p_at_1_short_focused_B": m_b["p_at_1"],
            }
        )

        # Phase 4 quick semantic sanity (for first 3 probe queries only).
        if len(qualitative_rows) < 3:
            base_top1 = cands[0]
            rerank_top_id = sorted(zip(doc_ids, raw_a), key=lambda x: (-x[1], x[0]))[0][0]
            rerank_top1 = next(c for c in cands if c.doc_id == rerank_top_id)
            judged_top_id = sorted(judged_map.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            judged_top1 = next(c for c in cands if c.doc_id == judged_top_id)
            qualitative_rows.append(
                {
                    "query_id": qid,
                    "query_text": q,
                    "base_top1": {"doc_id": base_top1.doc_id, "file": base_top1.file},
                    "rerank_top1": {"doc_id": rerank_top1.doc_id, "file": rerank_top1.file},
                    "judged_best": {
                        "doc_id": judged_top1.doc_id,
                        "file": judged_top1.file,
                        "judged_relevance": judged_map.get(judged_top1.doc_id, 0.0),
                    },
                    "five_line_explanation": quick_reason(
                        q,
                        {"doc_id": base_top1.doc_id, "file": base_top1.file},
                        {"doc_id": rerank_top1.doc_id, "file": rerank_top1.file},
                        {"doc_id": judged_top1.doc_id, "file": judged_top1.file, "judged_relevance": judged_map.get(judged_top1.doc_id, 0.0)},
                    ),
                }
            )

    con.close()

    tau_a = [r["metrics"]["A_original"]["kendall_tau"] for r in phase1_rows]
    tau_b = [r["metrics"]["B_focused"]["kendall_tau"] for r in phase1_rows]
    tau_c = [r["metrics"]["C_minimal_slice"]["kendall_tau"] for r in phase1_rows]
    p1_a = [r["metrics"]["A_original"]["p_at_1"] for r in phase1_rows]
    p1_b = [r["metrics"]["B_focused"]["p_at_1"] for r in phase1_rows]
    p1_c = [r["metrics"]["C_minimal_slice"]["p_at_1"] for r in phase1_rows]
    p3_a = [r["metrics"]["A_original"]["p_at_3"] for r in phase1_rows]
    p3_b = [r["metrics"]["B_focused"]["p_at_3"] for r in phase1_rows]
    p3_c = [r["metrics"]["C_minimal_slice"]["p_at_3"] for r in phase1_rows]

    delta_best_chunk = []
    for a, b, c in zip(tau_a, tau_b, tau_c):
        if a is None:
            continue
        candidates_tau = [x for x in [b, c] if x is not None]
        if not candidates_tau:
            continue
        delta_best_chunk.append(max(candidates_tau) - a)

    phase1_summary = {
        "mean_tau_A_original": mean_or_none(tau_a),
        "mean_tau_B_focused": mean_or_none(tau_b),
        "mean_tau_C_minimal_slice": mean_or_none(tau_c),
        "mean_tau_delta_B_minus_A": mean_or_none([r["delta_B_minus_A"] for r in compact_rows]),
        "mean_tau_delta_C_minus_A": mean_or_none([r["delta_C_minus_A"] for r in compact_rows]),
        "mean_tau_delta_best_reduced_minus_A": mean_or_none(delta_best_chunk),
        "mean_p_at_1_A_original": mean_or_none(p1_a),
        "mean_p_at_1_B_focused": mean_or_none(p1_b),
        "mean_p_at_1_C_minimal_slice": mean_or_none(p1_c),
        "mean_p_at_3_A_original": mean_or_none(p3_a),
        "mean_p_at_3_B_focused": mean_or_none(p3_b),
        "mean_p_at_3_C_minimal_slice": mean_or_none(p3_c),
    }

    tau_f1 = [r["metrics"]["format1_current"]["kendall_tau"] for r in phase2_rows]
    tau_f2 = [r["metrics"]["format2_query_code"]["kendall_tau"] for r in phase2_rows]
    tau_f3 = [r["metrics"]["format3_xmlish"]["kendall_tau"] for r in phase2_rows]
    p1_f1 = [r["metrics"]["format1_current"]["p_at_1"] for r in phase2_rows]
    p1_f2 = [r["metrics"]["format2_query_code"]["p_at_1"] for r in phase2_rows]
    p1_f3 = [r["metrics"]["format3_xmlish"]["p_at_1"] for r in phase2_rows]
    p3_f1 = [r["metrics"]["format1_current"]["p_at_3"] for r in phase2_rows]
    p3_f2 = [r["metrics"]["format2_query_code"]["p_at_3"] for r in phase2_rows]
    p3_f3 = [r["metrics"]["format3_xmlish"]["p_at_3"] for r in phase2_rows]
    delta_best_format = []
    for f1, f2, f3 in zip(tau_f1, tau_f2, tau_f3):
        if f1 is None:
            continue
        alts = [x for x in [f2, f3] if x is not None]
        if not alts:
            continue
        delta_best_format.append(max(alts) - f1)
    best_format_counts = {"format1_current": 0, "format2_query_code": 0, "format3_xmlish": 0}
    for r in phase2_rows:
        m = r["metrics"]
        ranked = sorted(
            [
                ("format1_current", m["format1_current"]["kendall_tau"]),
                ("format2_query_code", m["format2_query_code"]["kendall_tau"]),
                ("format3_xmlish", m["format3_xmlish"]["kendall_tau"]),
            ],
            key=lambda kv: (-float("-inf") if kv[1] is None else -kv[1], kv[0]),
        )
        best_format_counts[ranked[0][0]] += 1
    phase2_summary = {
        "mean_tau_format1_current": mean_or_none(tau_f1),
        "mean_tau_format2_query_code": mean_or_none(tau_f2),
        "mean_tau_format3_xmlish": mean_or_none(tau_f3),
        "mean_tau_delta_best_format_minus_current": mean_or_none(delta_best_format),
        "mean_p_at_1_format1_current": mean_or_none(p1_f1),
        "mean_p_at_1_format2_query_code": mean_or_none(p1_f2),
        "mean_p_at_1_format3_xmlish": mean_or_none(p1_f3),
        "mean_p_at_3_format1_current": mean_or_none(p3_f1),
        "mean_p_at_3_format2_query_code": mean_or_none(p3_f2),
        "mean_p_at_3_format3_xmlish": mean_or_none(p3_f3),
        "mean_cross_spearman_f1_vs_f2": mean_or_none(
            [r["cross_format_spearman"]["f1_vs_f2"] for r in phase2_rows]
        ),
        "mean_cross_spearman_f1_vs_f3": mean_or_none(
            [r["cross_format_spearman"]["f1_vs_f3"] for r in phase2_rows]
        ),
        "mean_cross_spearman_f2_vs_f3": mean_or_none(
            [r["cross_format_spearman"]["f2_vs_f3"] for r in phase2_rows]
        ),
        "best_format_counts": best_format_counts,
    }

    corr_len = [r["corr_length_vs_judged"] for r in phase3_rows]
    corr_lex = [r["corr_lexical_vs_judged"] for r in phase3_rows]
    corr_rerank = [r["corr_rerank_vs_judged"] for r in phase3_rows]
    p1_short_minus_long = [
        (r["p_at_1_short_focused_B"] - r["p_at_1_long_chunk_A"]) for r in phase3_rows
    ]
    phase3_summary = {
        "mean_corr_length_vs_judged": mean_or_none(corr_len),
        "mean_corr_lexical_vs_judged": mean_or_none(corr_lex),
        "mean_corr_rerank_vs_judged": mean_or_none(corr_rerank),
        "mean_corr_lexical_minus_rerank": mean_or_none(
            [
                (l - rr)
                for l, rr in zip(corr_lex, corr_rerank)
                if l is not None and rr is not None
            ]
        ),
        "mean_corr_length_minus_rerank": mean_or_none(
            [
                (ln - rr)
                for ln, rr in zip(corr_len, corr_rerank)
                if ln is not None and rr is not None
            ]
        ),
        "mean_p_at_1_short_focused_minus_long_original": mean_or_none(p1_short_minus_long),
    }

    mean_delta_chunk = phase1_summary["mean_tau_delta_best_reduced_minus_A"] or 0.0
    mean_delta_format = phase2_summary["mean_tau_delta_best_format_minus_current"] or 0.0
    mean_corr_lex = phase3_summary["mean_corr_lexical_vs_judged"] or 0.0
    mean_corr_len = phase3_summary["mean_corr_length_vs_judged"] or 0.0
    mean_corr_rr = phase3_summary["mean_corr_rerank_vs_judged"] or 0.0
    mean_tau_a = phase1_summary["mean_tau_A_original"] or 0.0
    mean_tau_b = phase1_summary["mean_tau_B_focused"] or 0.0
    mean_tau_c = phase1_summary["mean_tau_C_minimal_slice"] or 0.0

    chunk_material = mean_delta_chunk >= args.tau_gate
    format_material = mean_delta_format >= args.tau_gate
    eval_bias = (mean_corr_lex - mean_corr_rr >= 0.15) or (mean_corr_len - mean_corr_rr >= 0.15)
    rerank_weak = (mean_tau_a < 0.0 and mean_tau_b < 0.0 and mean_tau_c < 0.0)

    if chunk_material and format_material:
        if mean_delta_format >= mean_delta_chunk:
            root_cause = "input_contract"
            strength = mean_delta_format
        else:
            root_cause = "chunk_contamination"
            strength = mean_delta_chunk
    elif chunk_material:
        root_cause = "chunk_contamination"
        strength = mean_delta_chunk
    elif format_material:
        root_cause = "input_contract"
        strength = mean_delta_format
    elif eval_bias:
        root_cause = "evaluation_bias_toward_verbosity_or_lexical_match"
        strength = max(mean_corr_lex - mean_corr_rr, mean_corr_len - mean_corr_rr)
    elif rerank_weak:
        root_cause = "true_signal_weakness_for_domain"
        strength = abs(min(mean_tau_a, mean_tau_b, mean_tau_c))
    else:
        root_cause = "mixed_or_inconclusive"
        strength = 0.0

    if strength >= 0.15:
        confidence = "high"
    elif strength >= 0.08:
        confidence = "medium"
    else:
        confidence = "low"

    gate_improvement = max(mean_delta_chunk, mean_delta_format)
    full_sweep_gate_passed = gate_improvement >= args.tau_gate
    recommendation = "continue" if full_sweep_gate_passed else "halt"

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "alignment_json": str(args.alignment_json),
            "responses": str(args.responses),
            "duckdb_path": str(args.duckdb_path),
            "judge_config": str(args.judge_config),
            "seed_labels": str(args.seed_labels) if args.seed_labels else None,
            "reranker_model": args.reranker_model,
            "tau_gate": args.tau_gate,
        },
        "probe_selection": {
            "hurt": probe["hurt"],
            "helped_slightly": probe["helped_slightly"],
            "neutral_mixed": probe["neutral_mixed"],
            "selected": selected,
        },
        "phase1_chunk_contamination_test": {
            "summary": phase1_summary,
            "compact_per_query_deltas": compact_rows,
            "per_query": phase1_rows,
        },
        "phase2_formatting_contract_sensitivity": {
            "summary": phase2_summary,
            "per_query": phase2_rows,
        },
        "phase3_length_bias_audit": {
            "summary": phase3_summary,
            "per_query": phase3_rows,
        },
        "phase4_quick_semantic_sanity_check": qualitative_rows,
        "decision": {
            "root_cause_classification": root_cause,
            "confidence_level": confidence,
            "full_sweep_gate_passed": full_sweep_gate_passed,
            "recommendation": recommendation,
            "mean_tau_improvement_used_for_gate": gate_improvement,
        },
    }


def _fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def build_markdown_report(payload: dict[str, Any]) -> str:
    p1 = payload["phase1_chunk_contamination_test"]["summary"]
    p2 = payload["phase2_formatting_contract_sensitivity"]["summary"]
    p3 = payload["phase3_length_bias_audit"]["summary"]
    probe = payload["probe_selection"]
    dec = payload["decision"]
    compact = payload["phase1_chunk_contamination_test"]["compact_per_query_deltas"]

    lines: list[str] = []
    lines.append("# RERANKER ROOT-CAUSE TRIAGE REPORT (LIGHTWEIGHT)")
    lines.append("")
    lines.append(f"- Generated (UTC): `{payload['generated_utc']}`")
    lines.append(f"- Probe queries: `{probe['selected']}`")
    lines.append(f"- Hurt: `{probe['hurt']}`")
    lines.append(f"- Helped slightly: `{probe['helped_slightly']}`")
    lines.append(f"- Neutral/mixed: `{probe['neutral_mixed']}`")
    lines.append("")
    lines.append("## Compact Summary Table (Phase 1 A/B/C)")
    lines.append("")
    lines.append("| Variant | Mean Kendall tau vs judged | Mean P@1 | Mean P@3 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| A Original | {_fmt(p1['mean_tau_A_original'])} | {_fmt(p1['mean_p_at_1_A_original'])} | {_fmt(p1['mean_p_at_3_A_original'])} |"
    )
    lines.append(
        f"| B Focused | {_fmt(p1['mean_tau_B_focused'])} | {_fmt(p1['mean_p_at_1_B_focused'])} | {_fmt(p1['mean_p_at_3_B_focused'])} |"
    )
    lines.append(
        f"| C Minimal slice | {_fmt(p1['mean_tau_C_minimal_slice'])} | {_fmt(p1['mean_p_at_1_C_minimal_slice'])} | {_fmt(p1['mean_p_at_3_C_minimal_slice'])} |"
    )
    lines.append("")
    lines.append(
        f"- Mean tau delta (B-A): `{_fmt(p1['mean_tau_delta_B_minus_A'])}`"
    )
    lines.append(
        f"- Mean tau delta (C-A): `{_fmt(p1['mean_tau_delta_C_minus_A'])}`"
    )
    lines.append(
        f"- Mean tau delta (best reduced - A): `{_fmt(p1['mean_tau_delta_best_reduced_minus_A'])}`"
    )
    lines.append("")
    lines.append("## Per-Query Deltas")
    lines.append("")
    lines.append("| Query | Group | Label source | Tau A | Tau B | Tau C | B-A | C-A | P@1 A | P@1 B | P@1 C |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in compact:
        lines.append(
            f"| {r['query_id']} | {r['group']} | {r['label_source']} | {_fmt(r['tau_A'])} | {_fmt(r['tau_B'])} | {_fmt(r['tau_C'])} | {_fmt(r['delta_B_minus_A'])} | {_fmt(r['delta_C_minus_A'])} | {_fmt(r['p1_A'])} | {_fmt(r['p1_B'])} | {_fmt(r['p1_C'])} |"
        )
    lines.append("")
    lines.append("## Formatting Sensitivity (Phase 2)")
    lines.append("")
    lines.append("| Format | Mean Kendall tau | Mean P@1 | Mean P@3 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| Format 1 current | {_fmt(p2['mean_tau_format1_current'])} | {_fmt(p2['mean_p_at_1_format1_current'])} | {_fmt(p2['mean_p_at_3_format1_current'])} |"
    )
    lines.append(
        f"| Format 2 Query/Code | {_fmt(p2['mean_tau_format2_query_code'])} | {_fmt(p2['mean_p_at_1_format2_query_code'])} | {_fmt(p2['mean_p_at_3_format2_query_code'])} |"
    )
    lines.append(
        f"| Format 3 XML-like | {_fmt(p2['mean_tau_format3_xmlish'])} | {_fmt(p2['mean_p_at_1_format3_xmlish'])} | {_fmt(p2['mean_p_at_3_format3_xmlish'])} |"
    )
    lines.append("")
    lines.append(
        f"- Mean tau delta (best format - current): `{_fmt(p2['mean_tau_delta_best_format_minus_current'])}`"
    )
    lines.append(
        f"- Mean cross-format Spearman f1/f2: `{_fmt(p2['mean_cross_spearman_f1_vs_f2'])}`"
    )
    lines.append(
        f"- Mean cross-format Spearman f1/f3: `{_fmt(p2['mean_cross_spearman_f1_vs_f3'])}`"
    )
    lines.append("")
    lines.append("## Length & Lexical Bias (Phase 3)")
    lines.append("")
    lines.append(f"- Mean corr(length, judged): `{_fmt(p3['mean_corr_length_vs_judged'])}`")
    lines.append(f"- Mean corr(lexical overlap, judged): `{_fmt(p3['mean_corr_lexical_vs_judged'])}`")
    lines.append(f"- Mean corr(rerank, judged): `{_fmt(p3['mean_corr_rerank_vs_judged'])}`")
    lines.append(
        f"- Mean corr(lexical - rerank): `{_fmt(p3['mean_corr_lexical_minus_rerank'])}`"
    )
    lines.append(
        f"- Mean corr(length - rerank): `{_fmt(p3['mean_corr_length_minus_rerank'])}`"
    )
    lines.append("")
    lines.append("## Root-Cause Classification")
    lines.append("")
    lines.append(f"- ROOT_CAUSE = `{dec['root_cause_classification']}`")
    lines.append(f"- CONFIDENCE_LEVEL = `{dec['confidence_level']}`")
    lines.append(
        f"- Mean tau improvement used for gate = `{_fmt(dec['mean_tau_improvement_used_for_gate'])}`"
    )
    lines.append(f"- Full-sweep gate passed = `{dec['full_sweep_gate_passed']}`")
    lines.append(f"- Recommendation = `{dec['recommendation']}`")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    runs_root = ROOT / "eval" / "runs" / "reranker_eval_alignment_investigation"
    latest_alignment = None
    if runs_root.exists():
        cands = sorted(
            runs_root.glob("*/alignment_investigation.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if cands:
            latest_alignment = cands[0]
    if latest_alignment is None:
        latest_alignment = ROOT / "eval" / "runs" / "reranker_eval_alignment_investigation" / "20260219_041443" / "alignment_investigation.json"

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_out = ROOT / "eval" / "runs" / "reranker_root_cause_triage_light" / ts

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--alignment-json",
        type=Path,
        default=latest_alignment,
        help="Alignment investigation JSON used to select probe queries.",
    )
    parser.add_argument(
        "--responses",
        type=Path,
        default=ROOT / "eval" / "runs" / "stage2_geometry_lock_only_flags_repro" / "responses.jsonl",
        help="Responses JSONL containing query_id/query_text/run_id.",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=ROOT / "indexes" / "metadata.duckdb",
        help="DuckDB path to resolve candidate contents.",
    )
    parser.add_argument(
        "--seed-labels",
        type=Path,
        default=ROOT / "eval" / "runs" / "stage2_geometry_lock_only_flags_repro" / "candidate_signal_alignment_labels.jsonl",
        help="Optional existing judged-label cache to avoid fresh judging.",
    )
    parser.add_argument(
        "--judge-config",
        type=Path,
        default=ROOT / "eval" / "judge_config.json",
        help="Judge config for fallback live labeling.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Optional judge provider override.",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=None,
        help="Optional judge requests per minute override.",
    )
    parser.add_argument(
        "--reranker-model",
        type=str,
        default="tomaarsen/Qwen3-Reranker-0.6B-seq-cls",
    )
    parser.add_argument(
        "--content-chars",
        type=int,
        default=1600,
        help="Chars per candidate snippet in judge prompt.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_out,
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=ROOT / "docs" / "Audit of current system" / f"RERANKER_ROOT_CAUSE_TRIAGE_LIGHT_REPORT_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md",
    )
    parser.add_argument(
        "--tau-gate",
        type=float,
        default=0.10,
        help="Full sweep gate threshold on probe mean tau improvement.",
    )
    parser.add_argument("--skip-judge", action="store_true", help="Do not call judge; require seed/cache labels.")
    parser.add_argument(
        "--accept-partial-seed",
        action="store_true",
        help="Allow partial seed labels and fill missing with 0.",
    )
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "reranker_root_cause_triage_light.json"
    md_path = args.output_dir / "reranker_root_cause_triage_light.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_text = build_markdown_report(payload)
    md_path.write_text(md_text, encoding="utf-8")

    if args.report_md:
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text(md_text, encoding="utf-8")

    print(f"[OK] JSON: {json_path}")
    print(f"[OK] Markdown: {md_path}")
    if args.report_md:
        print(f"[OK] Report copy: {args.report_md}")


if __name__ == "__main__":
    main()
