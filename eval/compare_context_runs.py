from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "calls",
    "can",
    "do",
    "does",
    "during",
    "each",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "including",
    "into",
    "is",
    "it",
    "its",
    "layer",
    "layers",
    "me",
    "not",
    "of",
    "on",
    "or",
    "out",
    "over",
    "rank",
    "ranking",
    "run",
    "score",
    "should",
    "so",
    "that",
    "the",
    "their",
    "then",
    "there",
    "this",
    "through",
    "to",
    "trace",
    "under",
    "using",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
    "within",
    "without",
    "you",
    "your",
}


def _clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else 1.0 if x >= 1.0 else x


def _safe_div(n: float, d: float) -> float:
    if d == 0.0:
        return 0.0
    return n / d


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())


def _extract_concepts(query_text: str, limit: int = 32) -> list[str]:
    tokens = [t for t in _tokenize(query_text) if t not in _STOPWORDS]
    # Preserve ordering but de-dupe.
    seen: set[str] = set()
    concepts: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        concepts.append(token)
        if len(concepts) >= limit:
            break
    return concepts


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return _safe_div(inter, union)


def _entropy_from_probs(probs: Iterable[float]) -> float:
    ps = [p for p in probs if p > 0.0]
    if not ps:
        return 0.0
    h = 0.0
    for p in ps:
        h -= p * math.log(p, 2)
    # Normalize by max entropy for len(ps)
    max_h = math.log(len(ps), 2) if len(ps) > 1 else 1.0
    return _safe_div(h, max_h)


@dataclass(frozen=True)
class BlockMeta:
    chunk_id: str
    file_path: str | None
    span_start: int | None
    span_end: int | None
    entity_ids: list[str]
    content: str | None


def _load_run_ids(responses_path: Path) -> dict[int, str]:
    run_ids: dict[int, str] = {}
    for line in responses_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        run_ids[int(obj["query_id"])] = obj["run_id"]
    return run_ids


def _load_query_texts(responses_path: Path) -> dict[int, str]:
    q: dict[int, str] = {}
    for line in responses_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        q[int(obj["query_id"])] = obj["query_text"]
    return q


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _block_ids_from_context_diagnostics(cd: dict[str, Any]) -> list[dict[str, Any]]:
    # Current schema: top-level has level1/2/3. level1.result.blocks is authoritative.
    level1 = cd.get("level1") or {}
    result = level1.get("result") or {}
    blocks = result.get("blocks") or []
    # Each block minimally has block_id and tokens.
    return [b for b in blocks if isinstance(b, dict) and b.get("block_id")]


def _fetch_block_meta(con: duckdb.DuckDBPyConnection, chunk_id: str) -> BlockMeta:
    row = con.execute(
        "select chunk_id, file_path, span_start, span_end, entity_ids, content "
        "from chunks where chunk_id = ?",
        [chunk_id],
    ).fetchone()
    if not row:
        return BlockMeta(
            chunk_id=chunk_id,
            file_path=None,
            span_start=None,
            span_end=None,
            entity_ids=[],
            content=None,
        )
    entity_ids_raw = row[4]
    try:
        entity_ids = json.loads(entity_ids_raw) if entity_ids_raw else []
    except Exception:
        entity_ids = []
    content = row[5]
    return BlockMeta(
        chunk_id=row[0],
        file_path=row[1],
        span_start=row[2],
        span_end=row[3],
        entity_ids=entity_ids if isinstance(entity_ids, list) else [],
        content=content,
    )


def _span_overlap(a: BlockMeta, b: BlockMeta) -> float:
    if not a.file_path or not b.file_path or a.file_path != b.file_path:
        return 0.0
    if a.span_start is None or a.span_end is None or b.span_start is None or b.span_end is None:
        return 0.0
    start = max(a.span_start, b.span_start)
    end = min(a.span_end, b.span_end)
    if end < start:
        return 0.0
    overlap = (end - start) + 1
    len_a = (a.span_end - a.span_start) + 1
    len_b = (b.span_end - b.span_start) + 1
    denom = max(len_a, len_b, 1)
    return _safe_div(overlap, denom)


def _coverage_curve(concepts: list[str], metas: list[BlockMeta]) -> dict[str, Any]:
    if not concepts:
        return {
            "concepts": [],
            "coverage": [],
            "redundancy_jaccard": [],
            "plateau_index_95pct_final": 0,
        }

    concept_set = set(concepts)
    covered: set[str] = set()
    coverage: list[float] = []
    redundancy_jaccard: list[float] = []
    prev_union_tokens: set[str] = set()

    for meta in metas:
        text_parts = []
        if meta.file_path:
            text_parts.append(meta.file_path)
        if meta.content:
            # Avoid reading massive text into tokens; still good enough for coverage.
            text_parts.append(meta.content[:20_000])
        tokens = set(_tokenize(" ".join(text_parts)))
        newly = tokens & concept_set
        covered |= newly
        coverage.append(_safe_div(len(covered), len(concept_set)))
        redundancy_jaccard.append(_jaccard(prev_union_tokens, tokens))
        prev_union_tokens |= tokens

    final_cov = coverage[-1] if coverage else 0.0
    target = 0.95 * final_cov
    plateau = 0
    for i, c in enumerate(coverage, start=1):
        if c >= target:
            plateau = i
            break
    if plateau == 0:
        plateau = len(coverage)

    return {
        "concepts": concepts,
        "coverage": coverage,
        "redundancy_jaccard": redundancy_jaccard,
        "plateau_index_95pct_final": plateau,
    }


def _redundancy_level(metas: list[BlockMeta]) -> float:
    # Average same-file span overlap across all pairs.
    if len(metas) < 2:
        return 0.0
    overlaps: list[float] = []
    for i in range(len(metas)):
        for j in range(i + 1, len(metas)):
            overlaps.append(_span_overlap(metas[i], metas[j]))
    return float(sum(overlaps) / len(overlaps)) if overlaps else 0.0


def _concept_coverage_score(curve: dict[str, Any]) -> float:
    cov = curve.get("coverage") or []
    return float(cov[-1]) if cov else 0.0


def _tokens_per_block(blocks: list[dict[str, Any]]) -> list[int]:
    out: list[int] = []
    for b in blocks:
        try:
            out.append(int(b.get("tokens") or 0))
        except Exception:
            out.append(0)
    return out


def _semantic_entropy_from_blocks(blocks: list[dict[str, Any]]) -> float:
    # We don't have per-block semantic scores in context diagnostics; approximate from token mass.
    # If the distribution is extremely peaked, entropy is low (collapse risk).
    toks = [max(int(b.get("tokens") or 0), 0) for b in blocks]
    total = sum(toks)
    if total <= 0:
        return 0.0
    probs = [t / total for t in toks if t > 0]
    return _entropy_from_probs(probs)


def compute_run_metrics(
    run_dir: Path,
    artifacts_dir: Path,
    duckdb_path: Path,
    query_ids: list[int] | None,
) -> dict[str, Any]:
    responses_path = run_dir / "responses.jsonl"
    run_ids = _load_run_ids(responses_path)
    query_texts = _load_query_texts(responses_path)
    if query_ids is None:
        query_ids = sorted(run_ids.keys())

    con = duckdb.connect(str(duckdb_path), read_only=True)
    out: dict[str, Any] = {"run": run_dir.name, "queries": {}}

    for qid in query_ids:
        rid = run_ids.get(qid)
        if not rid:
            continue
        cd_path = artifacts_dir / rid / "context_diagnostics.json"
        tel_path = artifacts_dir / rid / "telemetry.json"
        if not cd_path.exists():
            continue
        cd = _read_json(cd_path)
        tel = _read_json(tel_path) if tel_path.exists() else {}

        blocks = _block_ids_from_context_diagnostics(cd)
        chunk_ids = [b["block_id"] for b in blocks]
        metas = [_fetch_block_meta(con, cid) for cid in chunk_ids]

        files = [m.file_path for m in metas if m.file_path]
        file_counts = Counter(files)
        distinct_files = len(file_counts)

        entities: set[str] = set()
        for m in metas:
            entities.update(m.entity_ids)

        concepts = _extract_concepts(query_texts.get(qid, ""))
        curve = _coverage_curve(concepts, metas)

        tokens_list = _tokens_per_block(blocks)
        total_tokens = sum(tokens_list)
        tokens_per_block = tokens_list

        # Telemetry truth for budget, if present.
        token_budget = (
            (((tel.get("phases") or {}).get("CONTEXT") or {}).get("token_budget"))
            if isinstance(tel.get("phases"), dict)
            else None
        )

        out["queries"][str(qid)] = {
            "run_id": rid,
            "context": {
                "blocks": len(blocks),
                "tokens_used": total_tokens,
                "token_budget": token_budget,
                "tokens_per_block": tokens_per_block,
                "distinct_files": distinct_files,
                "file_histogram": dict(file_counts),
                "distinct_entity_ids": len(entities),
                "redundancy_span_overlap": _redundancy_level(metas),
                "semantic_entropy_proxy": _semantic_entropy_from_blocks(blocks),
            },
            "concepts": {
                "concept_count": len(concepts),
                "concept_list": concepts,
                "coverage_score": _concept_coverage_score(curve),
                "coverage_curve": curve["coverage"],
                "redundancy_curve_jaccard": curve["redundancy_jaccard"],
                "coverage_plateau_index_95pct_final": curve["plateau_index_95pct_final"],
            },
            "notes": {
                "symbol_id_note": (
                    "Distinct symbol_id not available in chunks table; "
                    "reported distinct_entity_ids (from chunks.entity_ids) as a proxy."
                )
            },
        }

    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-run", required=True, help="e.g. eval/runs/run_YYYYMMDD_HHMMSS")
    ap.add_argument("--new-run", required=True, help="e.g. eval/runs/run_YYYYMMDD_HHMMSS")
    ap.add_argument("--artifacts", default="artifacts/runs")
    ap.add_argument("--duckdb", default="indexes/metadata.duckdb")
    ap.add_argument("--query-ids", default="", help="comma-separated, empty = all")
    ap.add_argument("--out", default="", help="optional json output path")
    args = ap.parse_args()

    old_run = Path(args.old_run)
    new_run = Path(args.new_run)
    artifacts = Path(args.artifacts)
    duckdb_path = Path(args.duckdb)

    if args.query_ids.strip():
        query_ids = [int(x) for x in args.query_ids.split(",") if x.strip()]
    else:
        query_ids = None

    old_metrics = compute_run_metrics(old_run, artifacts, duckdb_path, query_ids)
    new_metrics = compute_run_metrics(new_run, artifacts, duckdb_path, query_ids)

    report = {"old": old_metrics, "new": new_metrics}

    if args.out.strip():
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
