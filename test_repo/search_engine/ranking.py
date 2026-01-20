"""
Ranking engine for search results using similarity algorithms.
Uses numpy for mathematical operations - requires understanding of numpy logic.
"""

import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from config import settings

class RankingEngine:
    """
    Ranks search results using cosine similarity and other metrics.
    Math-heavy implementation that can return NaN in edge cases.
    """
    
    def __init__(self):
        """Initialize the ranking engine."""
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD
        self.default_top_k = settings.DEFAULT_TOP_K
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.
        Can return NaN if vectors are zero or invalid.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Cosine similarity score (0-1) or NaN if invalid
        """
        try:
            # Check for empty vectors
            if vec1.size == 0 or vec2.size == 0:
                return float('nan')
            
            # Calculate dot product
            dot_product = np.dot(vec1, vec2)
            
            # Calculate norms
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            # Check for zero norms (division by zero)
            if norm1 == 0 or norm2 == 0:
                return float('nan')
            
            # Cosine similarity
            similarity = dot_product / (norm1 * norm2)
            
            # Clamp to [0, 1]
            return max(0.0, min(1.0, similarity))
        except Exception:
            return float('nan')
    
    def combine_similarity_scores(self, scores: List[float], weights: Optional[List[float]] = None) -> float:
        """
        Combine multiple similarity scores into a single score.
        Uses weighted average if weights provided, otherwise simple average.
        
        Args:
            scores: List of similarity scores
            weights: Optional weights for each score
            
        Returns:
            Combined score or NaN if all scores are invalid
        """
        if not scores:
            return float('nan')
        
        # Filter out NaN values
        valid_scores = [s for s in scores if not np.isnan(s)]
        if not valid_scores:
            return float('nan')
        
        if weights:
            # Weighted average
            valid_weights = [w for s, w in zip(scores, weights) if not np.isnan(s)]
            if len(valid_weights) != len(valid_scores):
                return float('nan')
            
            weighted_sum = sum(s * w for s, w in zip(valid_scores, valid_weights))
            weight_sum = sum(valid_weights)
            
            if weight_sum == 0:
                return float('nan')
            
            return weighted_sum / weight_sum
        else:
            # Simple average
            return np.mean(valid_scores)
    
    def rank_results(self, query_embedding: np.ndarray, 
                    candidate_embeddings: List[Tuple[str, str, np.ndarray]]) -> List[Tuple[str, str, float]]:
        """
        Rank search results by similarity to query.
        Results are sorted by relevance (highest first).
        
        Args:
            query_embedding: Query vector
            candidate_embeddings: List of (file_path, entity_type, embedding) tuples
            
        Returns:
            Sorted list of (file_path, entity_type, score) tuples
        """
        scored_results = []
        
        for file_path, entity_type, embedding in candidate_embeddings:
            similarity = self.cosine_similarity(query_embedding, embedding)
            
            # Filter by threshold
            if not np.isnan(similarity) and similarity >= self.similarity_threshold:
                scored_results.append((file_path, entity_type, similarity))
        
        # Sort by score (descending) - this ensures results are sorted by relevance
        scored_results.sort(key=lambda x: x[2], reverse=True)
        
        return scored_results[:self.default_top_k]
    
    def rerank_with_filters(self, results: List[Tuple[str, str, float]],
                           filters: Dict[str, Any]) -> List[Tuple[str, str, float]]:
        """
        Rerank results with additional filters.
        
        Args:
            results: Initial ranked results
            filters: Filter criteria
            
        Returns:
            Filtered and reranked results
        """
        filtered = results
        
        # Apply entity type filter
        if 'entity_type' in filters:
            entity_type = filters['entity_type']
            filtered = [r for r in filtered if r[1] == entity_type]
        
        # Apply minimum score filter
        if 'min_score' in filters:
            min_score = filters['min_score']
            filtered = [r for r in filtered if r[2] >= min_score]
        
        # Re-sort to ensure relevance ordering
        filtered.sort(key=lambda x: x[2], reverse=True)
        
        return filtered
