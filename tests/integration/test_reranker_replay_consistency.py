import json
import os
from pathlib import Path

import duckdb
import pytest

from homllm.ranking.reranker import QwenReranker


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _resolve_candidate_payload(con: duckdb.DuckDBPyConnection, doc_ids: list[str]) -> dict[str, str]:
    if not doc_ids:
        return {}

    unique_doc_ids = list(dict.fromkeys(doc_ids))
    placeholders = ", ".join(["?"] * len(unique_doc_ids))
    out: dict[str, str] = {}

    chunk_rows = con.execute(
        f"""
        SELECT chunk_id, content
        FROM chunks
        WHERE chunk_id IN ({placeholders})
        """,
        unique_doc_ids,
    ).fetchall()
    for chunk_id, content in chunk_rows:
        out[str(chunk_id)] = str(content or "")

    unresolved = [doc_id for doc_id in unique_doc_ids if doc_id not in out]
    if not unresolved:
        return out

    symbol_ids = [doc_id.split(":", 1)[1] if ":" in doc_id else doc_id for doc_id in unresolved]
    sym_placeholders = ", ".join(["?"] * len(symbol_ids))
    sym_rows = con.execute(
        f"""
        SELECT symbol_id, content
        FROM symbols
        WHERE symbol_id IN ({sym_placeholders})
        """,
        symbol_ids,
    ).fetchall()
    by_symbol = {str(symbol_id): str(content or "") for symbol_id, content in sym_rows}
    for doc_id in unresolved:
        symbol_id = doc_id.split(":", 1)[1] if ":" in doc_id else doc_id
        if symbol_id in by_symbol:
            out[doc_id] = by_symbol[symbol_id]
    return out


def _rank_map_from_scores(scores: dict[str, float]) -> dict[str, int]:
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return {doc_id: idx for idx, (doc_id, _) in enumerate(ordered, start=1)}


def _spearman(rank_a: dict[str, int], rank_b: dict[str, int]) -> float:
    ids = sorted(set(rank_a) & set(rank_b))
    n = len(ids)
    if n < 2:
        return 1.0
    d2 = 0.0
    for doc_id in ids:
        d = float(rank_a[doc_id] - rank_b[doc_id])
        d2 += d * d
    return 1.0 - ((6.0 * d2) / (n * (n * n - 1.0)))


def _kendall(rank_a: dict[str, int], rank_b: dict[str, int]) -> float:
    ids = sorted(set(rank_a) & set(rank_b))
    n = len(ids)
    if n < 2:
        return 1.0
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            ida = ids[i]
            idb = ids[j]
            da = rank_a[ida] - rank_a[idb]
            db = rank_b[ida] - rank_b[idb]
            if da == 0 or db == 0:
                continue
            if (da > 0 and db > 0) or (da < 0 and db < 0):
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    if total == 0:
        return 1.0
    return (concordant - discordant) / float(total)


@pytest.mark.skipif(
    os.environ.get("HOMLLM_RUN_RERANKER_TESTS") != "1",
    reason="Set HOMLLM_RUN_RERANKER_TESTS=1 to run real-model reranker replay checks.",
)
def test_reranker_replay_matches_stored_ordering_fixture():
    labels_path = Path("eval/runs/stage2_geometry_lock_only_flags_repro/candidate_signal_alignment_labels.jsonl")
    duckdb_path = Path("indexes/metadata.duckdb")
    assert labels_path.exists(), f"Missing fixture: {labels_path}"
    assert duckdb_path.exists(), f"Missing DuckDB index: {duckdb_path}"

    rows = _read_jsonl(labels_path)
    ok_rows = [r for r in rows if r.get("status") == "OK"]
    assert ok_rows, "No OK rows in candidate alignment labels fixture"
    row = ok_rows[0]

    query = str(row.get("query_text", "")).strip()
    candidates = [c for c in row.get("candidates", []) if isinstance(c, dict)]
    assert query, "Fixture row missing query_text"
    assert candidates, "Fixture row missing candidates"

    doc_ids = [str(c.get("doc_id", "")).strip() for c in candidates if c.get("doc_id")]
    assert doc_ids, "No candidate doc_ids in fixture row"

    con = duckdb.connect(str(duckdb_path), read_only=True)
    payload = _resolve_candidate_payload(con, doc_ids)
    con.close()

    documents = [payload.get(doc_id) or doc_id for doc_id in doc_ids]
    stored_scores = {str(c["doc_id"]): float(c.get("rerank_score", 0.0) or 0.0) for c in candidates}

    reranker = QwenReranker("tomaarsen/Qwen3-Reranker-0.6B-seq-cls")
    assert reranker.healthcheck() is True

    if reranker._device == "cuda":
        raw_scores = reranker._batch_score_gpu(query, documents)
    else:
        raw_scores = reranker._batch_score_cpu(query, documents)
    replay_scores = {doc_id: float(score) for doc_id, score in zip(doc_ids, raw_scores)}

    rank_stored = _rank_map_from_scores(stored_scores)
    rank_replay = _rank_map_from_scores(replay_scores)

    spearman = _spearman(rank_stored, rank_replay)
    kendall = _kendall(rank_stored, rank_replay)

    assert spearman >= 0.95, f"Spearman too low: {spearman:.6f}"
    assert kendall >= 0.95, f"Kendall too low: {kendall:.6f}"
