from dataclasses import dataclass
from pathlib import Path

from homllm.common.config import Config
from homllm.common.types import Vector
from homllm.context.pipeline import ContextPipeline
from homllm.ranking.pipeline import RankingPipeline
from homllm.retrieval.pipeline import RetrievalPipeline

from homllm_v4.adapters.v3_context_adapter import V3ContextAdapter
from homllm_v4.adapters.v3_index_adapter import V3IndexAdapter
from homllm_v4.adapters.v3_ranking_adapter import V3RankingAdapter
from homllm_v4.adapters.v3_retrieval_adapter import V3RetrievalAdapter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


@dataclass(frozen=True)
class V3ReadOnlyComponents:
    service_registry: ServiceRegistry
    index_artifact_paths: dict[str, str]


class ZeroEmbedder:
    def __init__(self, dimension: int) -> None:
        self.dimension = int(dimension)
        self.tokenizer = None

    def embed_query(self, query: str) -> Vector:
        return Vector(tuple(0.0 for _ in range(self.dimension)))

    def embed_code(self, code: str) -> Vector:
        return Vector(tuple(0.0 for _ in range(self.dimension)))


def build_v3_read_only_components(
    config_path: Path,
    *,
    smoke_safe: bool = False,
) -> V3ReadOnlyComponents:
    config = Config.from_file(Path(config_path))
    indexer_config = config.get_indexer_config()
    retrieval_config = config.get_retrieval_config()
    ranking_config = config.get_ranking_config()
    context_config = config.get_context_config()

    embedder = None
    if smoke_safe:
        retrieval_config.parallel_search_enabled = False
        ranking_config.reranker_enabled = False
        embedder = ZeroEmbedder(indexer_config.embedding_dimension)

    retrieval_pipeline = RetrievalPipeline(
        retrieval_config,
        indexer_config.storage.tantivy_path,
        indexer_config.storage.lancedb_path,
        duckdb_path=indexer_config.storage.duckdb_path,
        artifacts_path=indexer_config.storage.artifacts_path,
        embedder=embedder,
    )
    ranking_pipeline = RankingPipeline(ranking_config)
    context_pipeline = ContextPipeline(context_config, embedder=embedder)

    registry = ServiceRegistry()
    registry.register("index.validate", IndexService(adapter=V3IndexAdapter()))
    registry.register(
        "evidence.retrieve",
        EvidenceRetrievalService(adapter=V3RetrievalAdapter(pipeline=retrieval_pipeline)),
    )
    registry.register(
        "evidence.rank",
        EvidenceRankingService(adapter=V3RankingAdapter(pipeline=ranking_pipeline)),
    )
    registry.register(
        "context.build",
        ContextPackService(adapter=V3ContextAdapter(pipeline=context_pipeline)),
    )

    return V3ReadOnlyComponents(
        service_registry=registry,
        index_artifact_paths={
            "duckdb": indexer_config.storage.duckdb_path.as_posix(),
            "tantivy": indexer_config.storage.tantivy_path.as_posix(),
            "lancedb": indexer_config.storage.lancedb_path.as_posix(),
            "artifacts": indexer_config.storage.artifacts_path.as_posix(),
        },
    )
