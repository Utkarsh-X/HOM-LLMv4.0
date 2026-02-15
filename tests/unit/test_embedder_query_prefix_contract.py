"""Unit tests for embed_query prefix ownership contract."""

import logging

import pytest

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
