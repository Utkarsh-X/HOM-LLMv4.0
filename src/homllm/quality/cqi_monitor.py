"""
CQI_4 Monitoring — Pure observability, no behavioral changes.

Computes dual-axis CQI_4 from telemetry drop_trace and adds to telemetry.
Called from run_query.py AFTER context assembly.

Architecture:
  Coherence Index:     CI  = α·z(M4) − β·z(M3)
  Ranking Confidence:  RCI = γ·z(M5) + δ·z(M6)
  CQI_4 = sigmoid(0.5·CI + 0.5·RCI)
"""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Drift-penalized weights ──
# w_i = |r_i| / (1 + drift_i)
# r values from BASE20 correlation, drift from 5-fold CV
ALPHA = 0.5682   # M4 in coherence axis
BETA  = 0.4318   # M3 in coherence axis (applied negative)
GAMMA = 0.5626   # M5 in ranking axis
DELTA = 0.4374   # M6 in ranking axis

EPSILON = 1e-6
Z_CLIP = 3.0

# Rolling window baselines (from BASE20, n=20)
# These will be updated as more data accumulates
BASELINES = {
    "M4_content_overlap":    {"mean": 0.197, "std": 0.180},
    "M3_file_entropy":       {"mean": 2.02,  "std": 0.59},
    "M5_score_separation":   {"mean": 0.091, "std": 0.049},
    "M6_reranker_influence":  {"mean": 0.188, "std": 0.094},
}


def _z(val: float, mean: float, std: float) -> float:
    z = (val - mean) / (std + EPSILON)
    return max(-Z_CLIP, min(Z_CLIP, z))


def _percentile_from_z(z: float) -> float:
    """Convert z-score to percentile using standard normal CDF approximation."""
    return round(0.5 * (1 + math.erf(z / math.sqrt(2))), 4)


def compute_cqi4_from_drop_trace(drop_trace: List[Dict]) -> Optional[Dict[str, Any]]:
    """Compute CQI_4 directly from a drop_trace list.
    
    This is the primary entry point — called from run_query.py with
    context_artifact.provenance.get("context_drop_trace").
    """
    if not drop_trace:
        return None
    return _compute_cqi4_core(drop_trace)


def _compute_cqi4_core(drop_trace: List[Dict]) -> Optional[Dict[str, Any]]:
    """Core CQI_4 computation from drop_trace blocks."""
    try:
        
        if not drop_trace:
            return None
        
        # M4: content_overlap
        kept = [b for b in drop_trace if b.get("drop_reason") == "kept"]
        if len(kept) >= 2:
            contents = [b.get("block_content", "") or "" for b in kept]
            tokens_list = [set(c.lower().split()) for c in contents if c]
            if len(tokens_list) >= 2:
                overlaps = []
                for i in range(len(tokens_list)):
                    for j in range(i + 1, len(tokens_list)):
                        if tokens_list[i] and tokens_list[j]:
                            inter = len(tokens_list[i] & tokens_list[j])
                            union = len(tokens_list[i] | tokens_list[j])
                            overlaps.append(inter / union if union > 0 else 0)
                m4 = sum(overlaps) / len(overlaps) if overlaps else 0
            else:
                m4 = 0
        else:
            m4 = 0
        
        # M3: file_entropy
        files = [b.get("file", "") for b in kept if b.get("file")]
        if len(files) >= 2:
            counts: Dict[str, int] = {}
            for f in files:
                counts[f] = counts.get(f, 0) + 1
            n = len(files)
            m3 = -sum((c / n) * math.log2(c / n) for c in counts.values())
        else:
            m3 = 0
        
        # M5: score_separation
        scores = sorted([b.get("final_score", 0) or 0 for b in drop_trace if b.get("final_score") is not None], reverse=True)
        if len(scores) >= 2:
            m5 = scores[0] - scores[-1]
        else:
            m5 = 0
        
        # M6: reranker_influence
        sem_scores = [b.get("semantic_score", 0) or 0 for b in drop_trace if b.get("semantic_score") is not None]
        final_scores = [b.get("final_score", 0) or 0 for b in drop_trace if b.get("final_score") is not None]
        if sem_scores and final_scores and len(sem_scores) == len(final_scores):
            diffs = [abs(f - s) for f, s in zip(final_scores, sem_scores)]
            m6 = sum(diffs) / len(diffs) if diffs else 0
        else:
            m6 = 0
        
        # Z-scores
        z4 = _z(m4, BASELINES["M4_content_overlap"]["mean"], BASELINES["M4_content_overlap"]["std"])
        z3 = _z(m3, BASELINES["M3_file_entropy"]["mean"], BASELINES["M3_file_entropy"]["std"])
        z5 = _z(m5, BASELINES["M5_score_separation"]["mean"], BASELINES["M5_score_separation"]["std"])
        z6 = _z(m6, BASELINES["M6_reranker_influence"]["mean"], BASELINES["M6_reranker_influence"]["std"])
        
        # Dual axes
        ci = ALPHA * z4 - BETA * z3
        rci = GAMMA * z5 + DELTA * z6
        cqi4 = 1.0 / (1.0 + math.exp(-(0.5 * ci + 0.5 * rci)))
        
        # Zone
        if cqi4 >= 0.65:
            zone = "high_confidence"
        elif cqi4 >= 0.50:
            zone = "good"
        elif cqi4 >= 0.35:
            zone = "ambiguous"
        else:
            zone = "structurally_weak"
        
        # Top/bottom contributors
        contributions = {
            "M4_content_overlap": ALPHA * z4 * 0.5,
            "M3_file_entropy": -BETA * z3 * 0.5,
            "M5_score_separation": GAMMA * z5 * 0.5,
            "M6_reranker_influence": DELTA * z6 * 0.5,
        }
        sorted_contribs = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "cqi4": round(cqi4, 4),
            "coherence_index": round(ci, 4),
            "ranking_confidence_index": round(rci, 4),
            "zone": zone,
            "metrics": {
                "M4_content_overlap": round(m4, 4),
                "M3_file_entropy": round(m3, 4),
                "M5_score_separation": round(m5, 4),
                "M6_reranker_influence": round(m6, 4),
            },
            "z_scores": {
                "z4": round(z4, 3),
                "z3": round(z3, 3),
                "z5": round(z5, 3),
                "z6": round(z6, 3),
            },
            # Tier 2: Fine-grained axis exposure (observation only)
            "axis_detail": {
                "CI_raw": round(ci, 4),
                "RCI_raw": round(rci, 4),
                "M3_percentile": _percentile_from_z(z3),
                "M4_percentile": _percentile_from_z(z4),
                "M5_percentile": _percentile_from_z(z5),
                "M6_percentile": _percentile_from_z(z6),
            },
            "coherence_delta": None,  # Populated by pipeline after Tier 2 coherence
            "contributions": contributions,
            "top_contributor": sorted_contribs[0][0],
            "bottom_contributor": sorted_contribs[-1][0],
        }
    except Exception as e:
        logger.warning(f"CQI_4 computation failed: {e}")
        return None


def compute_m7_callgraph_coverage(
    callgraph: dict,
    context_blocks: list,
    depth: int = 2,
) -> dict[str, Any]:
    """Compute M7: callgraph coverage ratio via file+line matching.

    M7 = edges_in_context / edges_in_relevant_subgraph

    Matches context blocks to callgraph nodes by checking if a node's line
    falls within a block's [start_line, end_line] range (same file hash).

    Args:
        callgraph: {caller_id: [callee_id, ...]} where IDs are "hash:symbol:line"
        context_blocks: list of objects with .file, .start_line, .end_line
        depth: max BFS depth for relevant subgraph (default=2)
    """
    if not callgraph or not context_blocks:
        return {"M7_raw": 0.0, "M7_percentile": 0.5, "edges_in_context": 0,
                "edges_in_relevant_subgraph": 0, "context_nodes_matched": 0}

    # Collect all callgraph node IDs
    all_cg_ids: set[str] = set()
    for caller, callees in callgraph.items():
        all_cg_ids.add(caller)
        for callee in callees:
            all_cg_ids.add(callee)

    # Parse callgraph IDs: "file_hash:symbol:line" -> (file_hash, line)
    cg_node_info: dict[str, tuple[str, int]] = {}
    for node_id in all_cg_ids:
        parts = node_id.split(":")
        if len(parts) >= 3:
            file_hash = parts[0]
            try:
                line = int(parts[-1])
                cg_node_info[node_id] = (file_hash, line)
            except ValueError:
                pass

    # Group callgraph nodes by file_hash
    cg_by_hash: dict[str, list[str]] = {}
    for node_id, (fhash, _) in cg_node_info.items():
        cg_by_hash.setdefault(fhash, []).append(node_id)

    # Build block line ranges per file
    block_ranges: list[tuple[int, int]] = []
    for block in context_blocks:
        f = getattr(block, "file", None)
        sl = getattr(block, "start_line", None)
        el = getattr(block, "end_line", None)
        if f and sl is not None and el is not None:
            block_ranges.append((int(sl), int(el)))

    # Match: for each callgraph node, check if its line falls in any block range
    context_cg_ids: set[str] = set()
    for node_id, (fhash, line) in cg_node_info.items():
        for start, end in block_ranges:
            if start <= line <= end:
                context_cg_ids.add(node_id)
                break

    if not context_cg_ids:
        return {"M7_raw": 0.0, "M7_percentile": 0.5, "edges_in_context": 0,
                "edges_in_relevant_subgraph": 0, "context_nodes_matched": 0}

    # BFS from matched nodes to depth
    reverse_graph: dict[str, list[str]] = {}
    for caller, callees in callgraph.items():
        for callee in callees:
            reverse_graph.setdefault(callee, []).append(caller)

    relevant: set[str] = set(context_cg_ids)
    frontier = set(context_cg_ids)
    for _ in range(depth):
        nxt: set[str] = set()
        for sym in frontier:
            for c in callgraph.get(sym, []):
                if c not in relevant:
                    nxt.add(c)
            for c in reverse_graph.get(sym, []):
                if c not in relevant:
                    nxt.add(c)
        relevant |= nxt
        frontier = nxt
        if not frontier:
            break

    edges_relevant = 0
    edges_in_context = 0
    for caller in relevant:
        for callee in callgraph.get(caller, []):
            if callee in relevant:
                edges_relevant += 1
                if caller in context_cg_ids and callee in context_cg_ids:
                    edges_in_context += 1

    m7_raw = edges_in_context / max(edges_relevant, 1)
    z7 = _z(m7_raw, 0.15, 0.12)
    m7_percentile = _percentile_from_z(z7)

    return {
        "M7_raw": round(m7_raw, 4),
        "M7_percentile": round(m7_percentile, 4),
        "edges_in_context": edges_in_context,
        "edges_in_relevant_subgraph": edges_relevant,
        "context_nodes_matched": len(context_cg_ids),
    }
