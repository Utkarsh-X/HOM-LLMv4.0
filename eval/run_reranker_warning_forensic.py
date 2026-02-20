"""Reranker warning forensic investigation (no ranking-logic changes).

This script isolates model loading, head integrity, semantic behavior, and
pipeline-vs-standalone scoring consistency for:
    tomaarsen/Qwen3-Reranker-0.6B-seq-cls
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Local import for pipeline comparison only.
import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from homllm.ranking.reranker import QwenReranker  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _tensor_norm(state: dict[str, Any], key: str) -> float | None:
    value = state.get(key)
    if value is None:
        return None
    if not isinstance(value, torch.Tensor):
        return None
    return float(torch.norm(value).item())


def _shape_of(state: dict[str, Any], key: str) -> list[int] | None:
    value = state.get(key)
    if value is None:
        return None
    if not isinstance(value, torch.Tensor):
        return None
    return list(value.shape)


def _classifier_keys(state_keys: list[str]) -> list[str]:
    suffixes = (
        "score.weight",
        "score.bias",
        "classifier.weight",
        "classifier.bias",
    )
    out = [k for k in state_keys if k.endswith(suffixes)]
    return sorted(out)


def _spearman(scores_a: dict[str, float], scores_b: dict[str, float]) -> float:
    ids = sorted(set(scores_a.keys()) & set(scores_b.keys()))
    n = len(ids)
    if n < 2:
        return 1.0

    def rank_map(scores: dict[str, float]) -> dict[str, int]:
        ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return {doc_id: idx + 1 for idx, (doc_id, _) in enumerate(ordered)}

    ra = rank_map({i: scores_a[i] for i in ids})
    rb = rank_map({i: scores_b[i] for i in ids})
    d2 = sum((ra[i] - rb[i]) ** 2 for i in ids)
    return 1.0 - ((6.0 * d2) / (n * (n * n - 1.0)))


def _resolve_candidate_payload(
    con: duckdb.DuckDBPyConnection, doc_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not doc_ids:
        return {}
    unique_doc_ids = list(dict.fromkeys(doc_ids))
    placeholders = ", ".join(["?"] * len(unique_doc_ids))
    out: dict[str, dict[str, Any]] = {}

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

    symbol_ids = [doc_id.split(":", 1)[1] if ":" in doc_id else doc_id for doc_id in unresolved]
    sym_placeholders = ", ".join(["?"] * len(symbol_ids))
    sym_rows = con.execute(
        f"""
        SELECT s.symbol_id, f.path, s.content, s.start_line, s.end_line
        FROM symbols s
        LEFT JOIN files f ON s.file_id = f.file_id
        WHERE s.symbol_id IN ({sym_placeholders})
        """,
        symbol_ids,
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


def _load_forensics(model_id: str) -> tuple[dict[str, Any], Any, Any]:
    warn_records: list[dict[str, str]] = []
    stderr_buf = io.StringIO()
    model = None
    tokenizer = None
    loading_info: dict[str, Any] = {}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with contextlib.redirect_stderr(stderr_buf):
            model, loading_info = AutoModelForSequenceClassification.from_pretrained(
                model_id,
                trust_remote_code=True,
                output_loading_info=True,
            )
            tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    for w in caught:
        warn_records.append(
            {
                "category": str(getattr(w, "category", "")),
                "message": str(getattr(w, "message", "")),
            }
        )

    stderr_text = stderr_buf.getvalue()
    state = model.state_dict()
    state_keys = list(state.keys())

    load_diag = {
        "model_id": model_id,
        "model_type": str(type(model)),
        "tokenizer_type": str(type(tokenizer)),
        "loading_info": {
            "missing_keys": [str(k) for k in loading_info.get("missing_keys", [])],
            "unexpected_keys": [str(k) for k in loading_info.get("unexpected_keys", [])],
            "mismatched_keys": [str(k) for k in loading_info.get("mismatched_keys", [])],
            "error_msgs": [str(k) for k in loading_info.get("error_msgs", [])],
        },
        "warnings": warn_records,
        "stderr": stderr_text,
        "config": {
            "architectures": list(getattr(model.config, "architectures", []) or []),
            "num_labels": int(getattr(model.config, "num_labels", 0) or 0),
            "model_type": str(getattr(model.config, "model_type", "")),
            "name_or_path": str(getattr(model.config, "_name_or_path", "")),
            "commit_hash": str(getattr(model.config, "_commit_hash", "")),
            "transformers_version": str(getattr(model.config, "transformers_version", "")),
        },
        "classifier_layer_keys": _classifier_keys(state_keys),
        "specific_keys": {
            "score.weight.exists": "score.weight" in state,
            "score.weight.shape": _shape_of(state, "score.weight"),
            "score.weight.norm": _tensor_norm(state, "score.weight"),
            "score.bias.exists": "score.bias" in state,
            "score.bias.shape": _shape_of(state, "score.bias"),
            "score.bias.norm": _tensor_norm(state, "score.bias"),
            "classifier.weight.exists": "classifier.weight" in state,
            "classifier.weight.shape": _shape_of(state, "classifier.weight"),
            "classifier.weight.norm": _tensor_norm(state, "classifier.weight"),
            "classifier.bias.exists": "classifier.bias" in state,
            "classifier.bias.shape": _shape_of(state, "classifier.bias"),
            "classifier.bias.norm": _tensor_norm(state, "classifier.bias"),
        },
        "potential_randomly_initialized_keys": [
            str(k) for k in loading_info.get("missing_keys", [])
        ],
        "state_dict_key_count": len(state_keys),
        "state_dict_keys": state_keys,
    }
    return load_diag, model, tokenizer


def _semantic_test(model: Any, tokenizer: Any) -> dict[str, Any]:
    pairs = [
        (
            "How does logging work?",
            "The logging module defines LogManager and handlers.",
            "high",
        ),
        (
            "How does logging work?",
            "This file defines image resizing utilities.",
            "moderate",
        ),
        (
            "How does logging work?",
            "Random unrelated configuration constants.",
            "irrelevant",
        ),
    ]
    queries = [q for q, _, _ in pairs]
    docs = [d for _, d, _ in pairs]
    inputs = tokenizer(
        queries,
        docs,
        padding=True,
        truncation=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits.detach().cpu().tolist()
    scores = [float(row[0]) if isinstance(row, list) else float(row) for row in logits]
    monotonic_expected = scores[0] > scores[1] > scores[2]
    ranking = sorted(
        [
            {
                "label": label,
                "query": q,
                "doc": d,
                "logit": float(s),
            }
            for (q, d, label), s in zip(pairs, scores)
        ],
        key=lambda x: -x["logit"],
    )
    return {
        "pairs": [
            {"query": q, "doc": d, "label": label}
            for q, d, label in pairs
        ],
        "logits": scores,
        "ranking_high_to_low": ranking,
        "monotonic_expected_high_gt_moderate_gt_irrelevant": monotonic_expected,
    }


def _pipeline_vs_standalone(
    model_id: str,
    model: Any,
    tokenizer: Any,
    responses_path: Path,
    query_id: int,
    top_k: int,
    duckdb_path: Path,
) -> dict[str, Any]:
    rows = read_jsonl(responses_path)
    by_qid = {int(r["query_id"]): r for r in rows if "query_id" in r}
    if query_id not in by_qid:
        raise RuntimeError(f"query_id {query_id} not found in {responses_path}")
    row = by_qid[query_id]
    run_id = str(row.get("run_id", "")).strip()
    query_text = str(row.get("query_text", "")).strip()
    if not run_id:
        raise RuntimeError(f"query_id {query_id} has no run_id in responses")

    diag_path = Path("artifacts") / "runs" / run_id / "candidate_diagnostics.json"
    if not diag_path.exists():
        raise RuntimeError(f"Missing candidate diagnostics: {diag_path}")
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    ranking = [r for r in (diag.get("ranking_top20") or []) if isinstance(r, dict)]
    ranking = ranking[:top_k]
    doc_ids = [str(r.get("doc_id", "")).strip() for r in ranking if r.get("doc_id")]

    con = duckdb.connect(str(duckdb_path), read_only=True)
    payload = _resolve_candidate_payload(con, doc_ids)
    con.close()

    docs = [payload.get(doc_id, {}).get("content", "") or doc_id for doc_id in doc_ids]
    files = [payload.get(doc_id, {}).get("file", "") for doc_id in doc_ids]

    # A) Standalone raw logits (pair mode).
    inputs_pair = tokenizer(
        [query_text for _ in docs],
        docs,
        padding=True,
        truncation=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        out_pair = model(**inputs_pair)
    standalone_logits = [
        float(v[0]) if isinstance(v, list) else float(v)
        for v in out_pair.logits.detach().cpu().tolist()
    ]

    # B) HOMLLM reranker raw scores (pipeline mode).
    os.environ["PYTHONPATH"] = str(SRC)
    reranker = QwenReranker(model_id)
    if not reranker.healthcheck():
        raise RuntimeError("HOMLLM reranker healthcheck failed in comparison step.")
    if reranker._device == "cuda":
        pipeline_raw = reranker._batch_score_gpu(query_text, docs)
    else:
        pipeline_raw = reranker._batch_score_cpu(query_text, docs)
    pipeline_raw = [float(x) for x in pipeline_raw]

    by_doc_a = {d: s for d, s in zip(doc_ids, standalone_logits)}
    by_doc_b = {d: s for d, s in zip(doc_ids, pipeline_raw)}
    spearman = _spearman(by_doc_a, by_doc_b)

    rows_out = []
    for i, doc_id in enumerate(doc_ids):
        rows_out.append(
            {
                "rank_input": i + 1,
                "doc_id": doc_id,
                "file": files[i],
                "standalone_pair_logit": standalone_logits[i],
                "pipeline_raw_logit": pipeline_raw[i],
                "abs_diff": abs(standalone_logits[i] - pipeline_raw[i]),
            }
        )

    return {
        "query_id": query_id,
        "run_id": run_id,
        "query_text": query_text,
        "top_k": top_k,
        "scores": rows_out,
        "summary": {
            "spearman_standalone_vs_pipeline": spearman,
            "mean_abs_diff": sum(r["abs_diff"] for r in rows_out) / float(len(rows_out) or 1),
            "max_abs_diff": max((r["abs_diff"] for r in rows_out), default=0.0),
        },
    }


def _write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reranker warning forensic investigation.")
    parser.add_argument("--model-id", default="tomaarsen/Qwen3-Reranker-0.6B-seq-cls")
    parser.add_argument(
        "--responses",
        type=Path,
        default=Path("eval/runs/stage1_lock_only_flags_repro/responses.jsonl"),
    )
    parser.add_argument("--query-id", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--duckdb-path", type=Path, default=Path("indexes/metadata.duckdb"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/runs/reranker_warning_forensic"),
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs/Audit of current system"),
    )
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    load_diag, model, tokenizer = _load_forensics(args.model_id)
    semantic = _semantic_test(model, tokenizer)
    comparison = _pipeline_vs_standalone(
        model_id=args.model_id,
        model=model,
        tokenizer=tokenizer,
        responses_path=args.responses,
        query_id=args.query_id,
        top_k=args.top_k,
        duckdb_path=args.duckdb_path,
    )

    load_json = run_dir / "load_diagnostic.json"
    semantic_json = run_dir / "semantic_test_results.json"
    compare_json = run_dir / "pipeline_vs_standalone_comparison.json"
    load_json.write_text(json.dumps(load_diag, ensure_ascii=False, indent=2), encoding="utf-8")
    semantic_json.write_text(json.dumps(semantic, ensure_ascii=False, indent=2), encoding="utf-8")
    compare_json.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    # Required markdown outputs.
    md1 = args.docs_dir / "RERANKER_LOAD_DIAGNOSTIC.md"
    md2 = args.docs_dir / "RERANKER_SEMANTIC_TEST_RESULTS.md"
    md3 = args.docs_dir / "RERANKER_PIPELINE_VS_STANDALONE_COMPARISON.md"

    _write_md(
        md1,
        [
            "# RERANKER LOAD DIAGNOSTIC",
            "",
            f"- Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}",
            f"- Model ID: `{args.model_id}`",
            f"- Model Type: `{load_diag['model_type']}`",
            f"- Tokenizer Type: `{load_diag['tokenizer_type']}`",
            "",
            "## Loading Info",
            f"- missing_keys: `{len(load_diag['loading_info']['missing_keys'])}`",
            f"- unexpected_keys: `{len(load_diag['loading_info']['unexpected_keys'])}`",
            f"- mismatched_keys: `{len(load_diag['loading_info']['mismatched_keys'])}`",
            f"- error_msgs: `{len(load_diag['loading_info']['error_msgs'])}`",
            "",
            "## Config",
            f"- architectures: `{load_diag['config']['architectures']}`",
            f"- num_labels: `{load_diag['config']['num_labels']}`",
            f"- model_type: `{load_diag['config']['model_type']}`",
            f"- commit_hash: `{load_diag['config']['commit_hash']}`",
            "",
            "## Classifier Inspection",
            f"- classifier_layer_keys: `{load_diag['classifier_layer_keys']}`",
            f"- score.weight exists: `{load_diag['specific_keys']['score.weight.exists']}`",
            f"- score.weight shape: `{load_diag['specific_keys']['score.weight.shape']}`",
            f"- score.weight norm: `{load_diag['specific_keys']['score.weight.norm']}`",
            f"- score.bias exists: `{load_diag['specific_keys']['score.bias.exists']}`",
            f"- score.bias shape: `{load_diag['specific_keys']['score.bias.shape']}`",
            f"- score.bias norm: `{load_diag['specific_keys']['score.bias.norm']}`",
            f"- classifier.weight exists: `{load_diag['specific_keys']['classifier.weight.exists']}`",
            f"- classifier.bias exists: `{load_diag['specific_keys']['classifier.bias.exists']}`",
            "",
            "## Warnings / stderr",
            f"- warnings_count: `{len(load_diag['warnings'])}`",
            "```text",
            load_diag["stderr"] or "(empty)",
            "```",
            "",
            "## Missing/Randomly Initialized Keys",
            "```json",
            json.dumps(load_diag["potential_randomly_initialized_keys"], indent=2),
            "```",
            "",
            "## Full Artifacts",
            f"- JSON: `{load_json}`",
        ],
    )

    _write_md(
        md2,
        [
            "# RERANKER SEMANTIC TEST RESULTS",
            "",
            f"- Model ID: `{args.model_id}`",
            "",
            "## Controlled Pairs",
            "```json",
            json.dumps(semantic["pairs"], indent=2),
            "```",
            "",
            "## Raw Logits",
            "```json",
            json.dumps(semantic["logits"], indent=2),
            "```",
            "",
            "## Ranking (High -> Low)",
            "```json",
            json.dumps(semantic["ranking_high_to_low"], indent=2),
            "```",
            "",
            f"- monotonic_expected_high_gt_moderate_gt_irrelevant: `{semantic['monotonic_expected_high_gt_moderate_gt_irrelevant']}`",
            "",
            "## Full Artifacts",
            f"- JSON: `{semantic_json}`",
        ],
    )

    _write_md(
        md3,
        [
            "# RERANKER PIPELINE VS STANDALONE COMPARISON",
            "",
            f"- Model ID: `{args.model_id}`",
            f"- Query ID: `{comparison['query_id']}`",
            f"- Run ID: `{comparison['run_id']}`",
            "",
            "## Query",
            "```text",
            comparison["query_text"],
            "```",
            "",
            "## Summary",
            f"- Spearman(standalone_pair_logit vs pipeline_raw_logit): `{comparison['summary']['spearman_standalone_vs_pipeline']}`",
            f"- Mean absolute diff: `{comparison['summary']['mean_abs_diff']}`",
            f"- Max absolute diff: `{comparison['summary']['max_abs_diff']}`",
            "",
            "## Top-K Candidate Scores",
            "| rank | doc_id | file | standalone_pair_logit | pipeline_raw_logit | abs_diff |",
            "|---:|---|---|---:|---:|---:|",
            *[
                f"| {r['rank_input']} | {r['doc_id']} | {r['file']} | {r['standalone_pair_logit']:.6f} | {r['pipeline_raw_logit']:.6f} | {r['abs_diff']:.6f} |"
                for r in comparison["scores"]
            ],
            "",
            "## Full Artifacts",
            f"- JSON: `{compare_json}`",
        ],
    )

    print(f"Saved load diagnostic json: {load_json}")
    print(f"Saved semantic test json: {semantic_json}")
    print(f"Saved comparison json: {compare_json}")
    print(f"Saved markdown: {md1}")
    print(f"Saved markdown: {md2}")
    print(f"Saved markdown: {md3}")
    print(json.dumps(
        {
            "load_missing_keys": len(load_diag["loading_info"]["missing_keys"]),
            "load_unexpected_keys": len(load_diag["loading_info"]["unexpected_keys"]),
            "semantic_monotonic": semantic["monotonic_expected_high_gt_moderate_gt_irrelevant"],
            "pipeline_vs_standalone_spearman": comparison["summary"]["spearman_standalone_vs_pipeline"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
