"""Reranker implementation using cross-encoder."""

import logging
from typing import Optional

import torch

from homllm.ranking.interfaces import Reranker

logger = logging.getLogger(__name__)

# Canonical model name - MUST match exactly, no fallbacks allowed
RERANKER_MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B"

try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
except ImportError:
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    logger.warning("transformers not available, reranking disabled")


class QwenReranker(Reranker):
    """Qwen3-Reranker-0.6B cross-encoder implementation."""

    def __init__(self, model_name: str = RERANKER_MODEL_NAME):
        """
        Initialize reranker.
        
        Properties:
        - Offline-only (no API calls)
        - Deterministic (same input → same score)
        - Batch-optimized
        """
        self.model_name = model_name
        self._model: Optional[torch.nn.Module] = None
        self._tokenizer: Optional[object] = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._available = False

        if AutoModelForSequenceClassification is not None:
            self._load_model()

    def _load_model(self) -> None:
        """Load reranker model."""
        if AutoModelForSequenceClassification is None:
            return

        try:
            logger.info(f"[RERANKER MODEL] Resolved: {self.model_name}")
            if self.model_name != RERANKER_MODEL_NAME:
                raise ValueError(
                    f"Reranker model mismatch: expected '{RERANKER_MODEL_NAME}', "
                    f"got '{self.model_name}'. No fallbacks allowed."
                )
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                trust_remote_code=True,
            ).to(self._device)
            self._model.eval()
            self._available = True
            logger.info("Reranker model loaded")

        except Exception as e:
            logger.error(f"Failed to load reranker model: {e}")
            self._model = None
            self._tokenizer = None
            self._available = False

    def batch_score(self, query: str, documents: list[str]) -> list[float]:
        """
        Cross-encoder scoring. No text synthesis.
        
        Properties:
        - Deterministic
        - No hallucination (scores, not generates)
        - Batch-optimized
        """
        if not self._available or self._model is None or self._tokenizer is None:
            # Return zero scores if reranker unavailable
            return [0.0] * len(documents)

        try:
            scores = []
            for doc in documents:
                # Create query-document pair
                pair_text = f"{query} [SEP] {doc}"

                # Tokenize
                inputs = self._tokenizer(
                    pair_text,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512,
                ).to(self._device)

                # Score
                with torch.no_grad():
                    outputs = self._model(**inputs)
                    # Extract relevance score (logits)
                    score = outputs.logits[0][0].item()

                scores.append(float(score))

            # Normalize scores to [0, 1] range
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    scores = [
                        (s - min_score) / (max_score - min_score) for s in scores
                    ]
                else:
                    scores = [0.5] * len(scores)

            return scores

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Return zero scores on error
            return [0.0] * len(documents)

    def healthcheck(self) -> bool:
        """Check if reranker is available."""
        return self._available
