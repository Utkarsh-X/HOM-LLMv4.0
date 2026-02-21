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
            "top_contributor": sorted_contribs[0][0],
            "bottom_contributor": sorted_contribs[-1][0],
        }
    except Exception as e:
        logger.warning(f"CQI_4 computation failed: {e}")
        return None
