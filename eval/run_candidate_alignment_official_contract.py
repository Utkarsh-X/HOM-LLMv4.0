"""BASE20 candidate-level alignment audit using official reranker contract.

No ranking geometry/selector/retrieval/context changes are performed.
This script reuses existing judged candidate labels and recomputes reranker
scores with the currently configured reranker implementation.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from homllm.ranking.reranker import QwenReranker  # noqa: E402


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
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return float(sum(nums) / len(nums))


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


def ordered_doc_ids(scores: dict[str, float]) -> list[str]:
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def precision_at_k(pred_order: list[str], gold_order: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    pred = pred_order[:k]
    gold = set(gold_order[:k])
    if not pred:
        return 0.0
    return len([d for d in pred if d in gold]) / float(k)


def _resolve_candidate_payload(
    con: duckdb.DuckDBPyConnection,
    doc_ids: list[str],
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


def classify_query_type(query: str) -> str:
    q = (query or "").lower()
    if any(k in q for k in ["bug", "fix", "error", "exception", "failing", "fails", "traceback"]):
        return "bug_fix"
    if any(k in q for k in ["api", "endpoint", "route", "lookup", "parameter", "request", "response"]):
        return "api_lookup"
    return "architecture"


def pct(n: int, d: int) -> float:
    return (100.0 * n / float(d)) if d else 0.0


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = [r for r in read_jsonl(args.labels) if str(r.get("status", "")).upper() == "OK"]
    if not rows:
        raise RuntimeError(f"No OK rows in labels file: {args.labels}")

    reranker = QwenReranker(args.reranker_model)
    if not reranker.healthcheck():
        raise RuntimeError("Reranker unavailable for official-contract alignment run.")

    con = duckdb.connect(str(args.duckdb_path), read_only=True)

    per_query: list[dict[str, Any]] = []
    strong_negative_threshold = float(args.strong_negative_tau_delta)

    for row in sorted(rows, key=lambda r: int(r.get("query_id", 0))):
        query_id = int(row["query_id"])
        query_text = str(row.get("query_text", ""))
        candidates = [c for c in row.get("candidates", []) if isinstance(c, dict)]
        doc_ids = [str(c.get("doc_id", "")) for c in candidates if c.get("doc_id")]
        payload = _resolve_candidate_payload(con, doc_ids)
        docs = [payload.get(doc_id, doc_id) for doc_id in doc_ids]

        base_map = {
            str(c["doc_id"]): float(c.get("base_score", 0.0) or 0.0)
            for c in candidates
        }
        judged_map = {
            str(c["doc_id"]): float(c.get("judged_relevance", 0.0) or 0.0)
            for c in candidates
        }

        rerank_scores = reranker.batch_score(query_text, docs)
        rerank_map = {
            doc_id: float(score) for doc_id, score in zip(doc_ids, rerank_scores)
        }
        diag = {}
        if hasattr(reranker, "get_last_batch_diagnostics"):
            last_diag = reranker.get_last_batch_diagnostics()
            if isinstance(last_diag, dict):
                diag = dict(last_diag)

        tau_base = kendall_tau_b(base_map, judged_map)
        tau_rerank = kendall_tau_b(rerank_map, judged_map)
        tau_delta = (
            None if tau_base is None or tau_rerank is None else (tau_rerank - tau_base)
        )

        base_order = ordered_doc_ids(base_map)
        rerank_order = ordered_doc_ids(rerank_map)
        judged_order = ordered_doc_ids(judged_map)
        p1_base = precision_at_k(base_order, judged_order, 1)
        p1_rerank = precision_at_k(rerank_order, judged_order, 1)
        p3_base = precision_at_k(base_order, judged_order, 3)
        p3_rerank = precision_at_k(rerank_order, judged_order, 3)

        per_query.append(
            {
                "query_id": query_id,
                "query_text": query_text,
                "query_type": classify_query_type(query_text),
                "tau_base_vs_judged": tau_base,
                "tau_rerank_official_vs_judged": tau_rerank,
                "tau_delta_rerank_minus_base": tau_delta,
                "p_at_1": {"base": p1_base, "rerank_official": p1_rerank},
                "p_at_3": {"base": p3_base, "rerank_official": p3_rerank},
                "reranker_telemetry": {
                    "rerank_input_token_length": float(diag.get("rerank_input_token_length", 0.0) or 0.0),
                    "truncation_rate": float(diag.get("truncation_rate", 0.0) or 0.0),
                    "raw_logit_std": float(diag.get("raw_logit_std", 0.0) or 0.0),
                    "sigmoid_std": float(diag.get("sigmoid_std", 0.0) or 0.0),
                },
                "strong_negative": bool(
                    tau_delta is not None and tau_delta <= strong_negative_threshold
                ),
            }
        )

    con.close()

    ok = per_query
    mean_tau_base = mean_or_none([r["tau_base_vs_judged"] for r in ok])
    mean_tau_rerank = mean_or_none([r["tau_rerank_official_vs_judged"] for r in ok])
    mean_tau_delta = mean_or_none([r["tau_delta_rerank_minus_base"] for r in ok])
    mean_p1_base = mean_or_none([r["p_at_1"]["base"] for r in ok])
    mean_p1_rerank = mean_or_none([r["p_at_1"]["rerank_official"] for r in ok])
    mean_p3_base = mean_or_none([r["p_at_3"]["base"] for r in ok])
    mean_p3_rerank = mean_or_none([r["p_at_3"]["rerank_official"] for r in ok])

    beats = [r for r in ok if (r["tau_delta_rerank_minus_base"] or 0.0) > 0.0]
    loses = [r for r in ok if (r["tau_delta_rerank_minus_base"] or 0.0) < 0.0]
    neutral = [r for r in ok if (r["tau_delta_rerank_minus_base"] or 0.0) == 0.0]
    strong_negative = [r for r in ok if r["strong_negative"]]

    gate_tau = (
        mean_tau_base is not None
        and mean_tau_rerank is not None
        and mean_tau_rerank >= (mean_tau_base + 0.05)
    )
    gate_p1 = (
        mean_p1_base is not None
        and mean_p1_rerank is not None
        and mean_p1_rerank >= mean_p1_base
    )
    gate_no_catastrophic = len(strong_negative) <= 3
    pass_all = gate_tau and gate_p1 and gate_no_catastrophic

    type_groups = {"api_lookup": [], "bug_fix": [], "architecture": []}
    for r in ok:
        type_groups.setdefault(r["query_type"], []).append(r)

    def summarize_group(rows_: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "queries": len(rows_),
            "mean_tau_base_vs_judged": mean_or_none([x["tau_base_vs_judged"] for x in rows_]),
            "mean_tau_rerank_official_vs_judged": mean_or_none([x["tau_rerank_official_vs_judged"] for x in rows_]),
            "mean_tau_delta_rerank_minus_base": mean_or_none([x["tau_delta_rerank_minus_base"] for x in rows_]),
            "mean_p_at_1_base": mean_or_none([x["p_at_1"]["base"] for x in rows_]),
            "mean_p_at_1_rerank_official": mean_or_none([x["p_at_1"]["rerank_official"] for x in rows_]),
            "mean_p_at_3_base": mean_or_none([x["p_at_3"]["base"] for x in rows_]),
            "mean_p_at_3_rerank_official": mean_or_none([x["p_at_3"]["rerank_official"] for x in rows_]),
        }

    by_type = {k: summarize_group(v) for k, v in type_groups.items()}

    aggregate = {
        "queries_ok": len(ok),
        "mean_tau": {
            "base_vs_judged": mean_tau_base,
            "rerank_official_vs_judged": mean_tau_rerank,
            "delta_rerank_minus_base": mean_tau_delta,
        },
        "mean_p_at_1": {"base": mean_p1_base, "rerank_official": mean_p1_rerank},
        "mean_p_at_3": {"base": mean_p3_base, "rerank_official": mean_p3_rerank},
        "queries_where_rerank_beats_base_pct": pct(len(beats), len(ok)),
        "queries_where_rerank_beats_base_count": len(beats),
        "queries_where_rerank_loses_to_base_count": len(loses),
        "queries_where_rerank_neutral_count": len(neutral),
        "strong_negative_tau_delta_threshold": strong_negative_threshold,
        "strong_negative_queries_count": len(strong_negative),
        "strong_negative_query_ids": [int(r["query_id"]) for r in strong_negative],
        "reranker_telemetry_means": {
            "rerank_input_token_length": mean_or_none(
                [r["reranker_telemetry"]["rerank_input_token_length"] for r in ok]
            ),
            "truncation_rate": mean_or_none(
                [r["reranker_telemetry"]["truncation_rate"] for r in ok]
            ),
            "raw_logit_std": mean_or_none(
                [r["reranker_telemetry"]["raw_logit_std"] for r in ok]
            ),
            "sigmoid_std": mean_or_none(
                [r["reranker_telemetry"]["sigmoid_std"] for r in ok]
            ),
        },
        "acceptance_gate": {
            "tau_gate": bool(gate_tau),
            "p_at_1_gate": bool(gate_p1),
            "no_catastrophic_degradation_gate": bool(gate_no_catastrophic),
            "pass_all": bool(pass_all),
        },
        "breakdown_by_query_type": by_type,
    }

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "labels": str(args.labels),
            "duckdb_path": str(args.duckdb_path),
            "reranker_model": args.reranker_model,
        },
        "aggregate": aggregate,
        "per_query": per_query,
    }


def build_markdown(payload: dict[str, Any]) -> str:
    a = payload["aggregate"]
    lines: list[str] = []
    lines.append("# BASE20 Candidate-Level Alignment (Official Reranker Contract)")
    lines.append("")
    lines.append(f"- Generated (UTC): `{payload['generated_utc']}`")
    lines.append(f"- Queries evaluated: `{a['queries_ok']}`")
    lines.append("")
    lines.append("## Core Metrics")
    lines.append("")
    lines.append(f"- tau(base, judged): `{a['mean_tau']['base_vs_judged']}`")
    lines.append(f"- tau(rerank_official, judged): `{a['mean_tau']['rerank_official_vs_judged']}`")
    lines.append(f"- mean tau delta (rerank - base): `{a['mean_tau']['delta_rerank_minus_base']}`")
    lines.append(f"- P@1 base vs rerank_official: `{a['mean_p_at_1']['base']}` vs `{a['mean_p_at_1']['rerank_official']}`")
    lines.append(f"- P@3 base vs rerank_official: `{a['mean_p_at_3']['base']}` vs `{a['mean_p_at_3']['rerank_official']}`")
    lines.append(f"- % queries rerank beats base (tau): `{a['queries_where_rerank_beats_base_pct']:.1f}%` ({a['queries_where_rerank_beats_base_count']}/{a['queries_ok']})")
    lines.append("")
    lines.append("## Telemetry Means")
    lines.append("")
    lines.append(f"- rerank_input_token_length: `{a['reranker_telemetry_means']['rerank_input_token_length']}`")
    lines.append(f"- truncation_rate: `{a['reranker_telemetry_means']['truncation_rate']}`")
    lines.append(f"- raw_logit_std: `{a['reranker_telemetry_means']['raw_logit_std']}`")
    lines.append(f"- sigmoid_std: `{a['reranker_telemetry_means']['sigmoid_std']}`")
    lines.append("")
    lines.append("## Acceptance Gate")
    lines.append("")
    lines.append(f"- tau gate (rerank >= base + 0.05): `{a['acceptance_gate']['tau_gate']}`")
    lines.append(f"- P@1 gate (rerank >= base): `{a['acceptance_gate']['p_at_1_gate']}`")
    lines.append(
        f"- No catastrophic degradation gate (<=3 strong negatives, threshold {a['strong_negative_tau_delta_threshold']}): "
        f"`{a['acceptance_gate']['no_catastrophic_degradation_gate']}` "
        f"(count={a['strong_negative_queries_count']}, qids={a['strong_negative_query_ids']})"
    )
    lines.append(f"- PASS ALL: `{a['acceptance_gate']['pass_all']}`")
    lines.append("")
    lines.append("## Per-Query")
    lines.append("")
    lines.append("| Query | Type | tau(base) | tau(rerank_official) | delta | P@1 base/rerank | P@3 base/rerank | token_len | trunc_rate | raw_logit_std | sigmoid_std |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(payload["per_query"], key=lambda x: int(x["query_id"])):
        lines.append(
            f"| {r['query_id']} | {r['query_type']} | "
            f"{r['tau_base_vs_judged']} | {r['tau_rerank_official_vs_judged']} | {r['tau_delta_rerank_minus_base']} | "
            f"{r['p_at_1']['base']:.3f}/{r['p_at_1']['rerank_official']:.3f} | "
            f"{r['p_at_3']['base']:.3f}/{r['p_at_3']['rerank_official']:.3f} | "
            f"{r['reranker_telemetry']['rerank_input_token_length']:.2f} | "
            f"{r['reranker_telemetry']['truncation_rate']:.4f} | "
            f"{r['reranker_telemetry']['raw_logit_std']:.4f} | "
            f"{r['reranker_telemetry']['sigmoid_std']:.4f} |"
        )
    lines.append("")
    lines.append("## Query-Type Breakdown")
    lines.append("")
    lines.append("| Type | Queries | mean tau(base) | mean tau(rerank) | mean delta | mean P@1 base/rerank | mean P@3 base/rerank |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for t, s in a["breakdown_by_query_type"].items():
        lines.append(
            f"| {t} | {s['queries']} | {s['mean_tau_base_vs_judged']} | {s['mean_tau_rerank_official_vs_judged']} | "
            f"{s['mean_tau_delta_rerank_minus_base']} | {s['mean_p_at_1_base']}/{s['mean_p_at_1_rerank_official']} | "
            f"{s['mean_p_at_3_base']}/{s['mean_p_at_3_rerank_official']} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_out = ROOT / "eval" / "runs" / "candidate_alignment_official_contract" / ts
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
        "--strong-negative-tau-delta",
        type=float,
        default=-0.15,
        help="Per-query tau delta threshold for strong negative cohort.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_out,
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=ROOT / "docs" / "Audit of current system" / f"BASE20_ALIGNMENT_OFFICIAL_CONTRACT_REPORT_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "base20_alignment_official_contract.json"
    md_path = args.output_dir / "base20_alignment_official_contract.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_text = build_markdown(payload)
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

