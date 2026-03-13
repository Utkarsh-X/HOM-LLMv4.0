"""Score fusion implementation."""

import logging
from typing import Optional

from homllm.ranking.interfaces import FeatureVector, RankConfig
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


class ScoreFusion:
    """Fuses base scores, rerank scores, and structural bonuses."""

    def compute_base_score(
        self, features: FeatureVector, config: RankConfig
    ) -> float:
        """
        Compute base score from features.
        
        Formula:
        base_score = (
            config.w_bm25 * bm25_percentile +
            config.w_dense * dense_percentile +
            config.w_name * name_match_score
        )
        """
        return (
            config.w_bm25 * features.bm25_percentile
            + config.w_dense * features.dense_percentile
            + config.w_name * features.name_match_score
            + config.w_broad_system_positive * features.broad_system_positive
            - config.w_broad_system_negative * features.broad_system_negative
        )

    def compute_struct_bonus(
        self, features: FeatureVector, config: RankConfig
    ) -> float:
        """
        Compute structural bonus.
        
        Bonuses for:
        - Entry points
        - Decorators
        - Callgraph proximity
        
        All weights from config. No hardcoded values.
        """
        bonus = 0.0

        if features.is_entrypoint:
            bonus += config.struct_entrypoint_bonus

        if features.has_decorator:
            bonus += config.struct_decorator_bonus

        # Callgraph distance bonus (already normalized to 0-1)
        bonus += features.callgraph_distance * config.struct_callgraph_bonus

        return min(bonus, config.struct_bonus_cap)

    def compute_final_score(
        self,
        base_score: float,
        rerank_score: float,
        struct_bonus: float,
        config: RankConfig,
    ) -> float:
        """
        Compute final score (weighted blend).
        
        Formula: final_score = (
            config.w_base * base_score +
            config.w_rerank * rerank_score +  # 0 if reranker disabled
            config.w_struct * struct_bonus
        )
        """
        return (
            config.w_base * base_score
            + config.w_rerank * rerank_score
            + config.w_struct * struct_bonus
        )
