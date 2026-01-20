"""Embedding model adapter."""

import logging
from typing import Optional

import numpy as np
import torch

from homllm.common.types import Vector
from homllm.indexer.interfaces import Embedder

logger = logging.getLogger(__name__)

# Canonical model name - MUST match exactly, no fallbacks allowed
EMBEDDING_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

try:
    from transformers import AutoModel, AutoTokenizer
except ImportError:
    AutoModel = None
    AutoTokenizer = None
    logger.warning("transformers not available, embedding disabled")


class QwenEmbedder(Embedder):
    """Qwen3-Embedding-0.6B embedder implementation."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, dimension: int = 1024):
        """
        Initialize embedder.
        
        Properties:
        - Offline-only (no API calls)
        - Deterministic (same input → same vector)
        - Model-agnostic (swappable via config)
        """
        self.model_name = model_name
        self._dimension = dimension
        self._model: Optional[torch.nn.Module] = None
        self._tokenizer: Optional[object] = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

        if AutoModel is not None and AutoTokenizer is not None:
            self._load_model()

    def _load_model(self) -> None:
        """Load embedding model."""
        if AutoModel is None or AutoTokenizer is None:
            return

        try:
            logger.info(f"[EMBEDDING MODEL] Resolved: {self.model_name}")
            if self.model_name != EMBEDDING_MODEL_NAME:
                raise ValueError(
                    f"Embedding model mismatch: expected '{EMBEDDING_MODEL_NAME}', "
                    f"got '{self.model_name}'. No fallbacks allowed."
                )
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(
                self.model_name,
                trust_remote_code=True,
            ).to(self._device)
            self._model.eval()  # Set to evaluation mode

            # Get actual dimension from model
            if hasattr(self._model, "config") and hasattr(
                self._model.config, "hidden_size"
            ):
                self._dimension = self._model.config.hidden_size

            logger.info(f"Model loaded, dimension: {self._dimension}")

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._model = None
            self._tokenizer = None

    def _embed_text(self, text: str, instruction_prefix: Optional[str] = None) -> Vector:
        """
        Internal embedding method.
        
        Args:
            text: Text to embed
            instruction_prefix: Optional instruction prefix for query embedding
        """
        if self._model is None or self._tokenizer is None:
            # Return zero vector as fallback
            return Vector(values=tuple([0.0] * self._dimension))

        try:
            # Prepare input text
            if instruction_prefix:
                input_text = f"{instruction_prefix}\n{text}"
            else:
                input_text = text

            # Tokenize
            inputs = self._tokenizer(
                input_text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(self._device)

            # Generate embeddings
            with torch.no_grad():
                outputs = self._model(**inputs)
                # Use mean pooling over sequence length
                embeddings = outputs.last_hidden_state.mean(dim=1).squeeze()

            # Normalize to unit vector
            embeddings = embeddings / torch.norm(embeddings)

            # Convert to tuple of floats
            values = tuple(embeddings.cpu().numpy().tolist())

            return Vector(values=values)

        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return Vector(values=tuple([0.0] * self._dimension))

    def embed_code(self, code: str) -> Vector:
        """
        Embeds code chunk. NO instruction prefix.
        
        FORBIDDEN: Embedding code with instruction prefixes.
        Code is embedded RAW.
        """
        return self._embed_text(code, instruction_prefix=None)

    def embed_query(self, query: str) -> Vector:
        """
        Embeds query WITH instruction prefix (asymmetric).
        
        Properties:
        - Instruction-aware for query side
        """
        # Use instruction prefix for query embedding
        instruction = "Represent this code search query for retrieval:"
        return self._embed_text(query, instruction_prefix=instruction)

    @property
    def dimension(self) -> int:
        """Returns embedding dimension. MUST be consistent."""
        return self._dimension
