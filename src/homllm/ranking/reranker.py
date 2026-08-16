"""Reranker implementation using cross-encoder."""

import logging
import math
import os
from typing import Any, Optional

try:
    import torch
except ImportError:
    # torch is only required to load the local cross-encoder model; without it
    # the reranker stays disabled (returns neutral scores). Lazy import lets the
    # ranking pipeline load without a GPU stack.
    torch = None  # type: ignore[assignment]

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

    DEFAULT_INSTRUCTION = (
        "Given a programming query, determine whether the provided code "
        "snippet directly answers, implements, or fixes the query intent."
    )
    SYSTEM_PROMPT = "Judge whether the Document meets the requirement of the Query."
    MAX_LENGTH = 8192
    GPU_BATCH_SIZE = 8
    CPU_BATCH_SIZE = 4

    def __init__(self, model_name: str = RERANKER_MODEL_NAME, device: str = "auto"):
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
        self._device = self._resolve_device(device)
        self._requested_device = device
        self._available = False
        self._head_validated = False
        self._load_error: Optional[str] = None
        self._loading_info: dict[str, Any] = {}
        self._instruction = os.environ.get(
            "HOMLLM_RERANKER_INSTRUCTION",
            self.DEFAULT_INSTRUCTION,
        ).strip() or self.DEFAULT_INSTRUCTION
        self._instruction_variant = (
            "env_override"
            if os.environ.get("HOMLLM_RERANKER_INSTRUCTION")
            else "default_programming_query"
        )
        self._last_batch_diagnostics: dict[str, float | str] = {
            "rerank_input_token_length": 0.0,
            "truncation_rate": 0.0,
            "instruction_variant": self._instruction_variant,
            "raw_logit_mean": 0.0,
            "raw_logit_std": 0.0,
            "sigmoid_mean": 0.0,
            "sigmoid_std": 0.0,
        }

        if AutoModelForSequenceClassification is not None:
            self._load_model()
        else:
            print("[RERANKER] transformers not available", flush=True)

    @staticmethod
    def _resolve_device(device: str) -> str:
        requested = (device or "auto").strip().lower()
        if requested not in {"auto", "cuda", "cpu"}:
            logger.warning("Unknown reranker device '%s', using auto", device)
            requested = "auto"
        if requested == "auto":
            if torch is None:
                return "cpu"
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested == "cuda" and (torch is None or not torch.cuda.is_available()):
            logger.warning("Reranker device 'cuda' requested but CUDA not available; using cpu")
            return "cpu"
        return requested

    @staticmethod
    def _is_head_key(name: str) -> bool:
        lowered = name.lower()
        return lowered.endswith("score.weight") or lowered.endswith("score.bias") or (
            lowered.endswith("classifier.weight") or lowered.endswith("classifier.bias")
        )

    @classmethod
    def _validate_loaded_head(
        cls,
        model: "torch.nn.Module",
        loading_info: dict[str, Any],
    ) -> None:
        """
        Validate that sequence-classification head parameters are present and loaded.

        Fail-fast if head weights were not loaded from checkpoint to avoid random
        initialization silently poisoning reranker quality.
        """
        state = model.state_dict()
        head_keys = [k for k in state.keys() if cls._is_head_key(k)]
        if not head_keys:
            raise RuntimeError(
                "Reranker head parameters not found in model state_dict "
                "(expected score/classifier head)."
            )

        missing_keys = [str(k) for k in (loading_info or {}).get("missing_keys", [])]
        missing_head = [k for k in missing_keys if cls._is_head_key(k)]
        if missing_head:
            raise RuntimeError(
                "Reranker checkpoint missing head parameters: "
                + ", ".join(sorted(missing_head))
            )

        # Validate score head shape when present.
        score_weight = state.get("score.weight")
        if score_weight is not None:
            if score_weight.ndim != 2:
                raise RuntimeError(
                    f"Invalid score.weight shape: expected 2D, got {tuple(score_weight.shape)}"
                )
            num_labels = int(getattr(model.config, "num_labels", 1) or 1)
            if int(score_weight.shape[0]) not in (1, num_labels):
                raise RuntimeError(
                    "Invalid score.weight output dimension: "
                    f"{tuple(score_weight.shape)} (num_labels={num_labels})"
                )

    def _load_model_for_device(self, device: str) -> None:
        """Load reranker model on a specific device."""
        if AutoModelForSequenceClassification is None:
            return
        self._device = device
        logger.info(f"[RERANKER MODEL] Resolved: {self.model_name}")
        if self.model_name != RERANKER_MODEL_NAME:
            logger.warning("Non-canonical reranker model: %s", self.model_name)

        offline_mode = os.environ.get("HOMLLM_OFFLINE", "0").strip() != "0"
        local_only = offline_mode
        resolved = resolve_snapshot_dir(self.model_name)
        model_source = str(resolved) if resolved is not None else self.model_name

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_source,
            trust_remote_code=True,
            local_files_only=local_only,
        )

        if self._tokenizer.pad_token is None:
            if self._tokenizer.eos_token is not None:
                self._tokenizer.pad_token = self._tokenizer.eos_token
                logger.info("Set pad_token to eos_token for batched inference")
            elif self._tokenizer.unk_token is not None:
                self._tokenizer.pad_token = self._tokenizer.unk_token
                logger.info("Set pad_token to unk_token for batched inference")
            else:
                self._tokenizer.add_special_tokens({"pad_token": "[PAD]"})
                logger.info("Added new [PAD] token for batched inference")

        dtype = torch.float16 if self._device == "cuda" else torch.float32
        use_device_map = False
        if self._device == "cuda":
            try:
                import accelerate  # noqa: F401
                use_device_map = True
            except Exception:
                use_device_map = False
        if self._device == "cuda" and not use_device_map:
            logger.warning(
                "accelerate not available; loading reranker without device_map"
            )

        load_kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            "local_files_only": local_only,
            "dtype": dtype,
        }
        if use_device_map:
            load_kwargs["device_map"] = "auto"

        try:
            self._model, loading_info = AutoModelForSequenceClassification.from_pretrained(
                model_source,
                output_loading_info=True,
                **load_kwargs,
            )
        except TypeError as exc:
            raise RuntimeError(
                "Reranker load requires transformers support for "
                "output_loading_info=True to validate head initialization."
            ) from exc
        if not use_device_map:
            self._model = self._model.to(self._device)

        if self._model.config.pad_token_id is None and self._tokenizer.pad_token_id is not None:
            self._model.config.pad_token_id = self._tokenizer.pad_token_id
            logger.info(f"Set model config pad_token_id to {self._tokenizer.pad_token_id}")

        self._loading_info = loading_info or {}
        self._validate_loaded_head(self._model, self._loading_info)
        self._head_validated = True
        self._model.eval()
        self._available = True
        self._load_error = None
        logger.info("Reranker model loaded on %s", self._device)

    def _load_model(self) -> None:
        """Load reranker model with optional GPU-to-CPU fallback."""
        if AutoModelForSequenceClassification is None:
            return
        try:
            self._load_model_for_device(self._device)
        except Exception as e:
            if self._device == "cuda":
                logger.warning(
                    "Reranker GPU init failed (%s). Retrying on CPU fallback.",
                    e,
                )
                try:
                    self._model = None
                    self._tokenizer = None
                    self._available = False
                    self._head_validated = False
                    self._load_model_for_device("cpu")
                    return
                except Exception as cpu_e:
                    self._load_error = str(cpu_e)
                    logger.error(f"Failed to load reranker model on CPU fallback: {cpu_e}")
            else:
                self._load_error = str(e)
                logger.error(f"Failed to load reranker model: {e}")
            self._model = None
            self._tokenizer = None
            self._available = False
            self._head_validated = False

    @classmethod
    def build_reranker_input(
        cls,
        instruction: Optional[str],
        query: str,
        document: str,
    ) -> str:
        """Build model input strictly following official chat-structured contract."""
        if instruction is None:
            instruction = cls.DEFAULT_INSTRUCTION

        prefix = (
            "<|im_start|>system\n"
            "Judge whether the Document meets the requirement of the Query.\n"
        )
        body = (
            f"<Instruct>: {instruction}\n"
            f"<Query>: {query}\n"
            f"<Document>: {document}\n"
        )
        suffix = (
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
            "<think>\n\n</think>\n"
        )
        return prefix + body + suffix

    @staticmethod
    def _safe_stats(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        mean = sum(values) / float(len(values))
        var = sum((v - mean) ** 2 for v in values) / float(len(values))
        return float(mean), float(math.sqrt(var))

    def _score_texts(
        self,
        texts: list[str],
    ) -> tuple[list[float], list[float], list[int], list[int]]:
        """
        Score pre-formatted texts with official transformer pattern.

        Returns:
            sigmoid_scores, raw_logits, truncated_flags, effective_lengths
        """
        if (
            not self._available
            or not self._head_validated
            or self._model is None
            or self._tokenizer is None
        ):
            n = len(texts)
            return [0.0] * n, [0.0] * n, [0] * n, [0] * n
        if not texts:
            return [], [], [], []

        raw_logits: list[float] = []
        sigmoid_scores: list[float] = []
        trunc_flags: list[int] = []
        effective_lengths: list[int] = []

        batch_size = self.GPU_BATCH_SIZE if self._device == "cuda" else self.CPU_BATCH_SIZE

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            pre_lengths = []
            for text in batch:
                encoded = self._tokenizer(
                    text,
                    add_special_tokens=True,
                    truncation=False,
                    return_attention_mask=False,
                )
                pre_lengths.append(len(encoded["input_ids"]))

            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.MAX_LENGTH,
                return_tensors="pt",
            )
            if self._device == "cuda":
                inputs = inputs.to("cuda")

            with torch.no_grad():
                out = self._model(**inputs).logits
                if out.dim() == 2 and out.size(1) == 1:
                    logits = out.squeeze(-1)
                else:
                    logits = out[:, 0]
                probs = torch.sigmoid(logits)
                raw_batch = logits.detach().cpu().tolist()
                prob_batch = probs.detach().cpu().tolist()

            if isinstance(raw_batch, float):
                raw_batch = [raw_batch]
            if isinstance(prob_batch, float):
                prob_batch = [prob_batch]

            eff_lengths = (
                inputs["attention_mask"]
                .detach()
                .cpu()
                .sum(dim=1)
                .tolist()
            )
            for pre_len, eff_len, raw_v, prob_v in zip(pre_lengths, eff_lengths, raw_batch, prob_batch):
                raw_logits.append(float(raw_v))
                sigmoid_scores.append(float(prob_v))
                effective_lengths.append(int(eff_len))
                trunc_flags.append(1 if pre_len > self.MAX_LENGTH else 0)

        return sigmoid_scores, raw_logits, trunc_flags, effective_lengths

    def _update_batch_diagnostics(
        self,
        raw_logits: list[float],
        sigmoid_scores: list[float],
        trunc_flags: list[int],
        effective_lengths: list[int],
    ) -> None:
        raw_mean, raw_std = self._safe_stats(raw_logits)
        sig_mean, sig_std = self._safe_stats(sigmoid_scores)
        mean_tokens, _ = self._safe_stats([float(v) for v in effective_lengths])
        truncation_rate, _ = self._safe_stats([float(v) for v in trunc_flags])
        self._last_batch_diagnostics = {
            "rerank_input_token_length": float(mean_tokens),
            "truncation_rate": float(truncation_rate),
            "instruction_variant": self._instruction_variant,
            "raw_logit_mean": float(raw_mean),
            "raw_logit_std": float(raw_std),
            "sigmoid_mean": float(sig_mean),
            "sigmoid_std": float(sig_std),
        }

    def get_last_batch_diagnostics(self) -> dict[str, float | str]:
        return dict(self._last_batch_diagnostics)

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
        
        if (
            not self._available
            or not self._head_validated
            or self._model is None
            or self._tokenizer is None
        ):
            self._update_batch_diagnostics([], [], [], [])
            return [0.0] * len(documents)

        if not documents:
            self._update_batch_diagnostics([], [], [], [])
            return []

        try:
            diag_start = time_module.perf_counter()

            texts = [
                self.build_reranker_input(self._instruction, query, doc)
                for doc in documents
            ]
            scores, raw_logits, trunc_flags, effective_lengths = self._score_texts(texts)
            self._update_batch_diagnostics(
                raw_logits=raw_logits,
                sigmoid_scores=scores,
                trunc_flags=trunc_flags,
                effective_lengths=effective_lengths,
            )

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
        """Backward-compatible raw scoring helper using official formatted inputs."""
        texts = [
            self.build_reranker_input(self._instruction, query, doc)
            for doc in documents
        ]
        _, raw_scores, _, _ = self._score_texts(texts)
        return raw_scores

    def _batch_score_cpu(self, query: str, documents: list[str]) -> list[float]:
        """Backward-compatible raw scoring helper using official formatted inputs."""
        texts = [
            self.build_reranker_input(self._instruction, query, doc)
            for doc in documents
        ]
        _, raw_scores, _, _ = self._score_texts(texts)
        return raw_scores

    def healthcheck(self) -> bool:
        """Check if reranker is available."""
        if not self._available or not self._head_validated:
            if self._load_error:
                logger.warning(
                    "Reranker unavailable: %s", self._load_error
                )
                print(
                    f"[RERANKER] unavailable: {self._load_error}",
                    flush=True,
                )
            else:
                logger.warning("Reranker unavailable: not loaded/validated")
                print("[RERANKER] unavailable: not loaded/validated", flush=True)
        return self._available and self._head_validated
