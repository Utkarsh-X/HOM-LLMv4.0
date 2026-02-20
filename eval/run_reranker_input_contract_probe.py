"""Phase-1 probe for official reranker input-contract enforcement.

Runs a controlled 6-query A/B:
- Baseline: legacy "[SEP]" concatenation with max_length=512 and min-max scaling
- Candidate: official chat-structured contract with max_length=8192 and sigmoid scores
"""

from __future__ import annotations

import argparse
import json
import math
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

from homllm.ranking.reranker import QwenReranker  # noqa: E402


PROBE_QUERIES = [5, 11, 13, 6, 2, 18]


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


def minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def mean(values: list[float]) -> float:
    return sum(values) / float(len(values)) if values else 0.0


def std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / float(len(values)))


def score_texts(
    model: Any,
    tokenizer: Any,
    device: str,
    texts: list[str],
    max_length: int,
) -> tuple[list[float], list[float], list[int], list[int]]:
    if not texts:
        return [], [], [], []

    pre_lengths: list[int] = []
    for t in texts:
        ids = tokenizer(
            t,
            add_special_tokens=True,
            truncation=False,
            return_attention_mask=False,
        )["input_ids"]
        pre_lengths.append(len(ids))

    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    if device == "cuda":
        inputs = inputs.to("cuda")

    with torch.no_grad():
        out = model(**inputs).logits
        if out.dim() == 2 and out.size(1) == 1:
            logits = out.squeeze(-1)
        else:
            logits = out[:, 0]
        probs = torch.sigmoid(logits)
        raw = logits.detach().cpu().tolist()
        sig = probs.detach().cpu().tolist()

    if isinstance(raw, float):
        raw = [raw]
    if isinstance(sig, float):
        sig = [sig]

    eff = inputs["attention_mask"].detach().cpu().sum(dim=1).tolist()
    trunc = [1 if p > max_length else 0 for p in pre_lengths]
    return [float(v) for v in raw], [float(v) for v in sig], trunc, [int(v) for v in eff]


def _resolve_candidate_payload(
    con: duckdb.DuckDBPyConnection, doc_ids: list[str]
) -> dict[str, str]:
    if not doc_ids:
        return {}
    uids = list(dict.fromkeys(doc_ids))
    ph = ", ".join(["?"] * len(uids))
    out: dict[str, str] = {}

    rows = con.execute(
        f"SELECT chunk_id, content FROM chunks WHERE chunk_id IN ({ph})",
        uids,
    ).fetchall()
    for cid, content in rows:
        out[str(cid)] = str(content or "")

    unresolved = [d for d in uids if d not in out]
    if unresolved:
        sym_ids = [d.split(":", 1)[1] if ":" in d else d for d in unresolved]
        sph = ", ".join(["?"] * len(sym_ids))
        srows = con.execute(
            f"SELECT symbol_id, content FROM symbols WHERE symbol_id IN ({sph})",
            sym_ids,
        ).fetchall()
        by_sym = {str(sid): str(content or "") for sid, content in srows}
        for d in unresolved:
            sid = d.split(":", 1)[1] if ":" in d else d
            if sid in by_sym:
                out[d] = by_sym[sid]
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = [r for r in read_jsonl(args.labels) if str(r.get("status", "")).upper() == "OK"]
    by_qid = {int(r["query_id"]): r for r in rows if "query_id" in r}
    missing = [qid for qid in PROBE_QUERIES if qid not in by_qid]
    if missing:
        raise RuntimeError(f"Missing probe queries in labels: {missing}")

    reranker = QwenReranker(args.reranker_model)
    if not reranker.healthcheck():
        raise RuntimeError("Reranker unavailable.")
    model = reranker._model
    tokenizer = reranker._tokenizer
    device = reranker._device
    if model is None or tokenizer is None:
        raise RuntimeError("Reranker model/tokenizer missing.")

    con = duckdb.connect(str(args.duckdb_path), read_only=True)

    per_query: list[dict[str, Any]] = []

    for qid in PROBE_QUERIES:
        row = by_qid[qid]
        query = str(row.get("query_text", "")).strip()
        candidates = [c for c in row.get("candidates", []) if isinstance(c, dict)]
        doc_ids = [str(c.get("doc_id", "")).strip() for c in candidates if c.get("doc_id")]
        payload = _resolve_candidate_payload(con, doc_ids)
        docs = [payload.get(doc_id, doc_id) for doc_id in doc_ids]

        judged = {str(c["doc_id"]): float(c.get("judged_relevance", 0.0) or 0.0) for c in candidates}

        legacy_texts = [f"{query} [SEP] {doc}" for doc in docs]
        legacy_raw, _, legacy_trunc, legacy_eff = score_texts(
            model=model,
            tokenizer=tokenizer,
            device=device,
            texts=legacy_texts,
            max_length=512,
        )
        legacy_scores = minmax(legacy_raw)
        legacy_map = {doc_id: score for doc_id, score in zip(doc_ids, legacy_scores)}

        official_texts = [
            QwenReranker.build_reranker_input(
                instruction=reranker._instruction,
                query=query,
                document=doc,
            )
            for doc in docs
        ]
        official_raw, official_sigmoid, official_trunc, official_eff = score_texts(
            model=model,
            tokenizer=tokenizer,
            device=device,
            texts=official_texts,
            max_length=8192,
        )
        official_map = {doc_id: score for doc_id, score in zip(doc_ids, official_sigmoid)}

        legacy_tau = kendall_tau_b(legacy_map, judged)
        official_tau = kendall_tau_b(official_map, judged)

        per_query.append(
            {
                "query_id": qid,
                "query_text": query,
                "legacy_sep": {
                    "kendall_tau_vs_judged": legacy_tau,
                    "p_at_1": precision_at_k(legacy_map, judged, 1),
                    "p_at_3": precision_at_k(legacy_map, judged, 3),
                    "truncation_rate": mean([float(v) for v in legacy_trunc]),
                    "input_token_length_mean": mean([float(v) for v in legacy_eff]),
                },
                "official_contract": {
                    "kendall_tau_vs_judged": official_tau,
                    "p_at_1": precision_at_k(official_map, judged, 1),
                    "p_at_3": precision_at_k(official_map, judged, 3),
                    "rerank_input_token_length": mean([float(v) for v in official_eff]),
                    "truncation_rate": mean([float(v) for v in official_trunc]),
                    "instruction_variant": reranker._instruction_variant,
                    "raw_logit_mean": mean(official_raw),
                    "raw_logit_std": std(official_raw),
                    "sigmoid_mean": mean(official_sigmoid),
                    "sigmoid_std": std(official_sigmoid),
                },
                "tau_delta_official_minus_legacy": (
                    None
                    if legacy_tau is None or official_tau is None
                    else (official_tau - legacy_tau)
                ),
            }
        )

    con.close()

    legacy_tau_vals = [float(r["legacy_sep"]["kendall_tau_vs_judged"]) for r in per_query if r["legacy_sep"]["kendall_tau_vs_judged"] is not None]
    official_tau_vals = [float(r["official_contract"]["kendall_tau_vs_judged"]) for r in per_query if r["official_contract"]["kendall_tau_vs_judged"] is not None]

    summary = {
        "mean_tau_legacy_sep": mean(legacy_tau_vals),
        "mean_tau_official_contract": mean(official_tau_vals),
        "mean_tau_improvement_official_minus_legacy": mean(
            [
                r["tau_delta_official_minus_legacy"]
                for r in per_query
                if r["tau_delta_official_minus_legacy"] is not None
            ]
        ),
        "mean_p_at_1_legacy_sep": mean([float(r["legacy_sep"]["p_at_1"]) for r in per_query]),
        "mean_p_at_1_official_contract": mean([float(r["official_contract"]["p_at_1"]) for r in per_query]),
        "mean_p_at_3_legacy_sep": mean([float(r["legacy_sep"]["p_at_3"]) for r in per_query]),
        "mean_p_at_3_official_contract": mean([float(r["official_contract"]["p_at_3"]) for r in per_query]),
        "mean_truncation_rate_legacy_sep": mean([float(r["legacy_sep"]["truncation_rate"]) for r in per_query]),
        "mean_truncation_rate_official_contract": mean([float(r["official_contract"]["truncation_rate"]) for r in per_query]),
        "mean_rerank_input_token_length_official_contract": mean(
            [float(r["official_contract"]["rerank_input_token_length"]) for r in per_query]
        ),
        "mean_raw_logit_mean_official_contract": mean(
            [float(r["official_contract"]["raw_logit_mean"]) for r in per_query]
        ),
        "mean_raw_logit_std_official_contract": mean(
            [float(r["official_contract"]["raw_logit_std"]) for r in per_query]
        ),
        "mean_sigmoid_mean_official_contract": mean(
            [float(r["official_contract"]["sigmoid_mean"]) for r in per_query]
        ),
        "mean_sigmoid_std_official_contract": mean(
            [float(r["official_contract"]["sigmoid_std"]) for r in per_query]
        ),
    }
    summary["acceptance_passed"] = (
        summary["mean_tau_improvement_official_minus_legacy"] >= args.tau_acceptance
    )

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "labels": str(args.labels),
            "duckdb_path": str(args.duckdb_path),
            "reranker_model": args.reranker_model,
            "tau_acceptance": args.tau_acceptance,
            "probe_queries": PROBE_QUERIES,
        },
        "summary": summary,
        "per_query": per_query,
    }


def build_markdown(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    lines: list[str] = []
    lines.append("# RERANKER INPUT CONTRACT PROBE (PHASE 1)")
    lines.append("")
    lines.append(f"- Generated (UTC): `{payload['generated_utc']}`")
    lines.append(f"- Probe queries: `{payload['inputs']['probe_queries']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Mean tau (legacy [SEP]): `{s['mean_tau_legacy_sep']:.4f}`")
    lines.append(f"- Mean tau (official contract): `{s['mean_tau_official_contract']:.4f}`")
    lines.append(
        f"- Mean tau improvement (official - legacy): `{s['mean_tau_improvement_official_minus_legacy']:.4f}`"
    )
    lines.append(f"- Mean P@1 legacy -> official: `{s['mean_p_at_1_legacy_sep']:.4f}` -> `{s['mean_p_at_1_official_contract']:.4f}`")
    lines.append(f"- Mean P@3 legacy -> official: `{s['mean_p_at_3_legacy_sep']:.4f}` -> `{s['mean_p_at_3_official_contract']:.4f}`")
    lines.append(f"- Mean truncation rate legacy -> official: `{s['mean_truncation_rate_legacy_sep']:.4f}` -> `{s['mean_truncation_rate_official_contract']:.4f}`")
    lines.append(f"- Mean rerank input token length (official): `{s['mean_rerank_input_token_length_official_contract']:.2f}`")
    lines.append(f"- Mean raw logit mean/std (official): `{s['mean_raw_logit_mean_official_contract']:.4f}` / `{s['mean_raw_logit_std_official_contract']:.4f}`")
    lines.append(f"- Mean sigmoid mean/std (official): `{s['mean_sigmoid_mean_official_contract']:.4f}` / `{s['mean_sigmoid_std_official_contract']:.4f}`")
    lines.append(f"- Acceptance (>= +0.10 tau improvement): `{s['acceptance_passed']}`")
    lines.append("")
    lines.append("## Per-Query")
    lines.append("")
    lines.append("| Query | Tau Legacy | Tau Official | Delta | P@1 Legacy | P@1 Official | P@3 Legacy | P@3 Official | Trunc Legacy | Trunc Official | TokLen Official | raw mean/std | sigmoid mean/std |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in payload["per_query"]:
        l = r["legacy_sep"]
        o = r["official_contract"]
        lines.append(
            "| {qid} | {tl:.4f} | {to:.4f} | {d:.4f} | {p1l:.4f} | {p1o:.4f} | {p3l:.4f} | {p3o:.4f} | {trl:.4f} | {tro:.4f} | {tok:.2f} | {rm:.4f}/{rs:.4f} | {sm:.4f}/{ss:.4f} |".format(
                qid=r["query_id"],
                tl=float(l["kendall_tau_vs_judged"] or 0.0),
                to=float(o["kendall_tau_vs_judged"] or 0.0),
                d=float(r["tau_delta_official_minus_legacy"] or 0.0),
                p1l=float(l["p_at_1"]),
                p1o=float(o["p_at_1"]),
                p3l=float(l["p_at_3"]),
                p3o=float(o["p_at_3"]),
                trl=float(l["truncation_rate"]),
                tro=float(o["truncation_rate"]),
                tok=float(o["rerank_input_token_length"]),
                rm=float(o["raw_logit_mean"]),
                rs=float(o["raw_logit_std"]),
                sm=float(o["sigmoid_mean"]),
                ss=float(o["sigmoid_std"]),
            )
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_out = ROOT / "eval" / "runs" / "reranker_input_contract_probe" / ts
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=ROOT / "eval" / "runs" / "stage2_geometry_lock_only_flags_repro" / "candidate_signal_alignment_labels.jsonl",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=ROOT / "indexes" / "metadata.duckdb",
    )
    parser.add_argument(
        "--reranker-model",
        type=str,
        default="tomaarsen/Qwen3-Reranker-0.6B-seq-cls",
    )
    parser.add_argument(
        "--tau-acceptance",
        type=float,
        default=0.10,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_out,
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=ROOT / "docs" / "Audit of current system" / f"RERANKER_INPUT_CONTRACT_PROBE_REPORT_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "reranker_input_contract_probe.json"
    md_path = args.output_dir / "reranker_input_contract_probe.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md = build_markdown(payload)
    md_path.write_text(md, encoding="utf-8")
    if args.report_md:
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        args.report_md.write_text(md, encoding="utf-8")
    print(f"[OK] JSON: {json_path}")
    print(f"[OK] Markdown: {md_path}")
    if args.report_md:
        print(f"[OK] Report copy: {args.report_md}")


if __name__ == "__main__":
    main()
