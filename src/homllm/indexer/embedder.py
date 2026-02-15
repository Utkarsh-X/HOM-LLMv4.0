"""Embedding model adapter."""

import logging
import os
from typing import Optional

import numpy as np
import torch

from homllm.common.types import Vector
from homllm.common.hf_cache import resolve_snapshot_dir
from homllm.indexer.interfaces import Embedder

logger = logging.getLogger(__name__)

# Canonical model name - MUST match exactly, no fallbacks allowed
EMBEDDING_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
QUERY_EMBED_INSTRUCTION = "Represent this code search query for retrieval:"

try:
    from transformers import AutoModel, AutoTokenizer
except ImportError:
    AutoModel = None
    AutoTokenizer = None
    logger.warning("transformers not available, embedding disabled")


class QwenEmbedder(Embedder):
    """Qwen3-Embedding-0.6B embedder implementation."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        dimension: int = 1024,
        max_input_tokens: int = 8192,
    ):
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
        self._requested_max_input_tokens = max_input_tokens
        self._effective_max_input_tokens = max_input_tokens
        self._query_input_log_count = 0

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

            # Prefer local snapshot dir (avoids hub API calls even when cached).
            # If not found, fall back to repo-id loading (may download).
            offline_mode = os.environ.get("HOMLLM_OFFLINE", "0").strip() != "0"
            local_only = offline_mode
            resolved = resolve_snapshot_dir(self.model_name)
            model_source = str(resolved) if resolved is not None else self.model_name

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_source,
                local_files_only=local_only,
            )
            self._model = AutoModel.from_pretrained(
                model_source,
                trust_remote_code=True,
                local_files_only=local_only,
            ).to(self._device)
            self._model.eval()  # Set to evaluation mode

            # Get actual dimension from model
            if hasattr(self._model, "config") and hasattr(
                self._model.config, "hidden_size"
            ):
                self._dimension = self._model.config.hidden_size

            model_max = getattr(self._model.config, "max_position_embeddings", None)
            if isinstance(model_max, int) and model_max > 0:
                self._effective_max_input_tokens = min(
                    self._requested_max_input_tokens,
                    model_max,
                )
            else:
                self._effective_max_input_tokens = self._requested_max_input_tokens

            logger.info(
                "Model loaded, dimension: %s, embed_max_tokens: %s",
                self._dimension,
                self._effective_max_input_tokens,
            )

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
            # Silent zero vectors create hard-to-detect regressions in retrieval and diagnostics.
            # Allow explicit opt-in for experiments/tests only.
            if os.environ.get("HOMLLM_ALLOW_ZERO_EMBEDDINGS", "0").strip() == "1":
                return Vector(values=tuple([0.0] * self._dimension))
            raise RuntimeError(
                "Embedding model is not loaded. Either pre-download the model to the HF cache, "
                "or set HOMLLM_OFFLINE=0 to allow downloads, or set HOMLLM_ALLOW_ZERO_EMBEDDINGS=1 "
                "to force a degraded zero-vector fallback."
            )

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
                max_length=self._effective_max_input_tokens,
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
            if os.environ.get("HOMLLM_ALLOW_ZERO_EMBEDDINGS", "0").strip() == "1":
                return Vector(values=tuple([0.0] * self._dimension))
            raise

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
        if QUERY_EMBED_INSTRUCTION in query:
            raise ValueError(
                "embed_query expects raw query text without instruction prefix"
            )

        input_text = f"{QUERY_EMBED_INSTRUCTION}\n{query}"
        prefix_count = input_text.count(QUERY_EMBED_INSTRUCTION)
        if prefix_count != 1:
            raise ValueError(
                f"Query embed prefix contract violated: expected 1, got {prefix_count}"
            )

        if self._query_input_log_count < 5:
            self._query_input_log_count += 1
            logger.info(
                "[EMBED_QUERY_INPUT] sample=%d prefix_count=%d input=%r",
                self._query_input_log_count,
                prefix_count,
                input_text,
            )

        return self._embed_text(query, instruction_prefix=QUERY_EMBED_INSTRUCTION)

    @property
    def dimension(self) -> int:
        """Returns embedding dimension. MUST be consistent."""
        return self._dimension
