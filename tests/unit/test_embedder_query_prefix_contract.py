"""Unit tests for embed_query prefix ownership contract."""

import logging
from types import SimpleNamespace

import pytest
import torch

import homllm.indexer.embedder as embedder_module
from homllm.common.types import Vector


def _make_embedder_without_model(monkeypatch: pytest.MonkeyPatch) -> embedder_module.QwenEmbedder:
    monkeypatch.setattr(embedder_module, "AutoModel", None)
    monkeypatch.setattr(embedder_module, "AutoTokenizer", None)
    return embedder_module.QwenEmbedder()


def test_embed_query_adds_single_instruction_prefix(monkeypatch: pytest.MonkeyPatch):
    embedder = _make_embedder_without_model(monkeypatch)
    calls: list[tuple[str, str | None]] = []

    def fake_embed_text(text: str, instruction_prefix: str | None = None) -> Vector:
        calls.append((text, instruction_prefix))
        return Vector(values=(1.0, 0.0))

    monkeypatch.setattr(embedder, "_embed_text", fake_embed_text)

    vector = embedder.embed_query("find auth function")

    assert vector.values == (1.0, 0.0)
    assert len(calls) == 1
    assert calls[0][0] == "find auth function"
    assert calls[0][1] == embedder_module.QUERY_EMBED_INSTRUCTION


def test_embed_query_rejects_prefixed_input(monkeypatch: pytest.MonkeyPatch):
    embedder = _make_embedder_without_model(monkeypatch)
    monkeypatch.setattr(
        embedder,
        "_embed_text",
        lambda text, instruction_prefix=None: Vector(values=(1.0, 0.0)),
    )

    prefixed = (
        f"{embedder_module.QUERY_EMBED_INSTRUCTION} "
        "find auth function"
    )
    with pytest.raises(ValueError, match="raw query text without instruction prefix"):
        embedder.embed_query(prefixed)


def test_embed_query_logs_input_for_first_five_queries(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    embedder = _make_embedder_without_model(monkeypatch)
    monkeypatch.setattr(
        embedder,
        "_embed_text",
        lambda text, instruction_prefix=None: Vector(values=(1.0, 0.0)),
    )

    with caplog.at_level(logging.INFO):
        for i in range(6):
            embedder.embed_query(f"query-{i}")

    lines = [
        record.message
        for record in caplog.records
        if record.message.startswith("[EMBED_QUERY_INPUT]")
    ]
    assert len(lines) == 5


def test_embed_text_converts_bfloat16_embeddings_to_float_vector():
    embedder = embedder_module.QwenEmbedder.__new__(embedder_module.QwenEmbedder)
    embedder._model = lambda **_: SimpleNamespace(
        last_hidden_state=torch.tensor([[[1.0, 2.0], [3.0, 4.0]]], dtype=torch.bfloat16)
    )
    embedder._tokenizer = lambda *_, **__: _TokenBatch({"input_ids": torch.tensor([[1, 2]])})
    embedder._device = "cpu"
    embedder._dimension = 2
    embedder._effective_max_input_tokens = 8

    vector = embedder._embed_text("find auth")

    assert len(vector.values) == 2
    assert all(isinstance(value, float) for value in vector.values)


class _TokenBatch(dict):
    def to(self, device: str):
        return self
