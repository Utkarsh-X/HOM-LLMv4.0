from types import SimpleNamespace

from homllm.common.types import ChunkInfo
from homllm.indexer.pipeline import IndexerPipeline


class _FakeTokenizer:
    def encode(self, text: str):
        return text.split()


def test_build_chunk_artifact_entry_includes_line_and_token_counts():
    pipeline = IndexerPipeline.__new__(IndexerPipeline)
    pipeline.embedder = SimpleNamespace(tokenizer=_FakeTokenizer())

    chunk = ChunkInfo(
        chunk_id="abc123",
        file_path="src/app.py",
        content="def run():\n    return value",
        granularity_level="fine",
        span_start=10,
        span_end=11,
        entity_ids=("e1",),
    )

    out = pipeline._build_chunk_artifact_entry(chunk)
    assert out["line_count"] == 2
    assert out["token_count"] == 4
    assert out["granularity_level"] == "fine"


def test_build_chunk_diagnostics_artifact_summarizes_granularity_mix():
    pipeline = IndexerPipeline.__new__(IndexerPipeline)
    pipeline.embedder = SimpleNamespace(
        tokenizer=_FakeTokenizer(),
        _effective_max_input_tokens=10,
    )
    pipeline.config = SimpleNamespace(chunk_max_lines=100)

    chunks = [
        ChunkInfo(
            chunk_id="f1",
            file_path="src/app.py",
            content="def run():\n    return value",
            granularity_level="fine",
            span_start=1,
            span_end=2,
        ),
        ChunkInfo(
            chunk_id="m1",
            file_path="src/app.py",
            content="class App:\n    pass\n\ndef run():\n    return value",
            granularity_level="medium",
            span_start=1,
            span_end=4,
        ),
    ]

    out = pipeline._build_chunk_diagnostics_artifact(chunks)
    assert out["total_chunks"] == 2
    assert out["granularity_counts"]["fine"] == 1
    assert out["granularity_counts"]["medium"] == 1
    assert out["all_chunks"]["line_count"]["median"] == 3.0
    assert out["embedding_max_tokens"] == 10
