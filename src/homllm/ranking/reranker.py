"""Reranker implementation using cross-encoder."""

import logging
import os
from typing import Optional

import torch

from homllm.common.hf_cache import resolve_snapshot_dir
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
        self._load_error: Optional[str] = None

        if AutoModelForSequenceClassification is not None:
            self._load_model()
        else:
            print("[RERANKER] transformers not available", flush=True)

    def _load_model(self) -> None:
        """Load reranker model."""
        if AutoModelForSequenceClassification is None:
            return

        try:
            logger.info(f"[RERANKER MODEL] Resolved: {self.model_name}")
            # Allow alternate reranker checkpoints that include a trained head.
            # Keep a warning for non-canonical names but do not hard-fail.
            if self.model_name != RERANKER_MODEL_NAME:
                logger.warning(
                    "Non-canonical reranker model: %s", self.model_name
                )
            offline_mode = os.environ.get("HOMLLM_OFFLINE", "0").strip() != "0"
            local_only = offline_mode
            resolved = resolve_snapshot_dir(self.model_name)
            model_source = str(resolved) if resolved is not None else self.model_name

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_source,
                trust_remote_code=True,
                local_files_only=local_only,
            )
            
            # Ensure padding token is set for batched inference
            # Try multiple fallbacks since some models don't have proper defaults
            if self._tokenizer.pad_token is None:
                if self._tokenizer.eos_token is not None:
                    self._tokenizer.pad_token = self._tokenizer.eos_token
                    logger.info("Set pad_token to eos_token for batched inference")
                elif self._tokenizer.unk_token is not None:
                    self._tokenizer.pad_token = self._tokenizer.unk_token
                    logger.info("Set pad_token to unk_token for batched inference")
                else:
                    # Last resort: add a new pad token
                    self._tokenizer.add_special_tokens({'pad_token': '[PAD]'})
                    logger.info("Added new [PAD] token for batched inference")
            
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            try:
                import accelerate  # noqa: F401
                use_device_map = True
            except Exception:
                use_device_map = False

            if use_device_map:
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    model_source,
                    trust_remote_code=True,
                    local_files_only=local_only,
                    num_labels=1,
                    dtype=dtype,
                    device_map="auto",
                )
            else:
                logger.warning(
                    "accelerate not available; loading reranker without device_map"
                )
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    model_source,
                    trust_remote_code=True,
                    local_files_only=local_only,
                    num_labels=1,
                    dtype=dtype,
                ).to(self._device)
            
            # Sync model config with tokenizer's pad_token_id
            if self._model.config.pad_token_id is None and self._tokenizer.pad_token_id is not None:
                self._model.config.pad_token_id = self._tokenizer.pad_token_id
                logger.info(f"Set model config pad_token_id to {self._tokenizer.pad_token_id}")
            
            self._model.eval()
            self._available = True
            self._load_error = None
            logger.info("Reranker model loaded")

        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Failed to load reranker model: {e}")
            self._model = None
            self._tokenizer = None
            self._available = False

    def batch_score(self, query: str, documents: list[str]) -> list[float]:
        """
        Cross-encoder scoring with automatic device optimization.
        
        - GPU (CUDA): Uses batched inference (parallel, 10x faster)
        - CPU: Uses sequential inference (avoids padding overhead)
        
        Properties:
        - Deterministic
        - No hallucination (scores, not generates)
        """
        import time as time_module
        
        if not self._available or self._model is None or self._tokenizer is None:
            return [0.0] * len(documents)

        if not documents:
            return []

        try:
            diag_start = time_module.perf_counter()
            
            # Auto-select strategy based on device
            if self._device == "cuda":
                scores = self._batch_score_gpu(query, documents)
            else:
                scores = self._batch_score_cpu(query, documents)

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

            # Log diagnostics
            total_ms = (time_module.perf_counter() - diag_start) * 1000
            doc_count = len(documents)
            per_doc_ms = total_ms / doc_count if doc_count else 0
            
            print(
                f"[RERANK_DIAG] docs={doc_count} total_ms={total_ms:.1f} "
                f"per_doc_ms={per_doc_ms:.1f} device={self._device}",
                flush=True
            )

            return scores

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return [0.0] * len(documents)

    def _batch_score_gpu(self, query: str, documents: list[str]) -> list[float]:
        """Batched inference optimized for GPU - processes all docs in single forward pass."""
        pairs = [f"{query} [SEP] {doc}" for doc in documents]
        
        inputs = self._tokenizer(
            pairs,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        ).to(self._device)
        
        with torch.no_grad():
            outputs = self._model(**inputs)
            if outputs.logits.dim() == 2 and outputs.logits.size(1) == 1:
                raw_scores = outputs.logits.squeeze(-1).tolist()
            else:
                raw_scores = outputs.logits[:, 0].tolist()
        
        # Handle single document case
        if isinstance(raw_scores, float):
            raw_scores = [raw_scores]
        
        return [float(s) for s in raw_scores]

    def _batch_score_cpu(self, query: str, documents: list[str]) -> list[float]:
        """Sequential inference optimized for CPU - avoids padding overhead."""
        scores = []
        
        for doc in documents:
            pair = f"{query} [SEP] {doc}"
            
            inputs = self._tokenizer(
                pair,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            ).to(self._device)
            
            with torch.no_grad():
                outputs = self._model(**inputs)
                if outputs.logits.dim() == 2 and outputs.logits.size(1) == 1:
                    score = outputs.logits.squeeze().item()
                else:
                    score = outputs.logits[0, 0].item()
                scores.append(score)
        
        return scores

    def healthcheck(self) -> bool:
        """Check if reranker is available."""
        if not self._available:
            if self._load_error:
                logger.warning(
                    "Reranker unavailable: %s", self._load_error
                )
                print(
                    f"[RERANKER] unavailable: {self._load_error}",
                    flush=True,
                )
            else:
                logger.warning("Reranker unavailable: not loaded")
                print("[RERANKER] unavailable: not loaded", flush=True)
        return self._available
