from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextPack, ContextPackRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import EvidenceRetrievalRequest
from homllm_v4.contracts.index import IndexRequest
from homllm_v4.contracts.policy import CapabilityPolicy
from homllm_v4.contracts.ranking import EvidenceRankingRequest
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.ledger.events import (
    CONTEXT_COMPLETED,
    INDEX_VALIDATED,
    POLICY_CREATED,
    RANKING_COMPLETED,
    RETRIEVAL_COMPLETED,
    RUN_COMPLETED,
    RUN_STARTED,
    SERVICE_FAILED,
    RunEvent,
)
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


def build_readonly_context(
    *,
    task_id: str,
    run_id: str,
    workspace_root: str,
    query: str,
    service_registry: ServiceRegistry,
    artifact_manager: ArtifactManager,
    event_writer: EventWriter,
    policy: CapabilityPolicy,
) -> CapabilityResult[ContextPack]:
    _ = artifact_manager
    _append(event_writer, run_id, task_id, "created", RUN_STARTED, {"query": query})
    _append(
        event_writer,
        run_id,
        task_id,
        "policy",
        POLICY_CREATED,
        {"permission_profile": policy.permission_profile},
    )

    index_service = service_registry.get("index.validate", IndexService)
    index_result = index_service.validate(
        IndexRequest(
            workspace_root=workspace_root,
            include_patterns=("**/*.py",),
            exclude_patterns=(".git/**",),
            language_profile="python",
            mode="validate",
            artifact_paths={},
        )
    )
    if not index_result.ok:
        _append(event_writer, run_id, task_id, "index", SERVICE_FAILED, {"service": "index.validate"})
        return _failed_context(index_result)
    _append(event_writer, run_id, task_id, "index", INDEX_VALIDATED, {"ok": True})

    retrieval_service = service_registry.get("evidence.retrieve", EvidenceRetrievalService)
    retrieval_result = retrieval_service.retrieve(
        EvidenceRetrievalRequest(
            task_id=task_id,
            query=query,
            task_class="answer",
            index_id=index_result.output.manifest.index_id,
            policy={},
        )
    )
    if not retrieval_result.ok:
        _append(
            event_writer,
            run_id,
            task_id,
            "retrieval",
            SERVICE_FAILED,
            {"service": "evidence.retrieve"},
        )
        return _failed_context(retrieval_result)
    if not retrieval_result.output.candidates:
        _append(
            event_writer,
            run_id,
            task_id,
            "retrieval",
            SERVICE_FAILED,
            {"service": "evidence.retrieve", "reason": "empty"},
        )
        return CapabilityResult(
            capability_name="context.build_readonly",
            ok=False,
            output=None,
            error=CapabilityError(
                code="empty_evidence_set",
                message="retrieval returned no candidates",
                recoverable=True,
                retryable=False,
                details={},
            ),
            telemetry=_telemetry(),
            artifacts=(),
        )
    _append(
        event_writer,
        run_id,
        task_id,
        "retrieval",
        RETRIEVAL_COMPLETED,
        {"candidate_count": len(retrieval_result.output.candidates)},
    )

    ranking_service = service_registry.get("evidence.rank", EvidenceRankingService)
    ranking_result = ranking_service.rank(
        EvidenceRankingRequest(task_id=task_id, evidence_set=retrieval_result.output, policy={})
    )
    if not ranking_result.ok:
        _append(event_writer, run_id, task_id, "ranking", SERVICE_FAILED, {"service": "evidence.rank"})
        return _failed_context(ranking_result)
    _append(
        event_writer,
        run_id,
        task_id,
        "ranking",
        RANKING_COMPLETED,
        {"item_count": len(ranking_result.output.items)},
    )

    context_service = service_registry.get("context.build", ContextPackService)
    context_result = context_service.build(
        ContextPackRequest(
            task_id=task_id,
            ranked_evidence_set=ranking_result.output,
            policy={},
            query=query,
        )
    )
    if not context_result.ok:
        _append(event_writer, run_id, task_id, "context", SERVICE_FAILED, {"service": "context.build"})
        return context_result
    _append(
        event_writer,
        run_id,
        task_id,
        "context",
        CONTEXT_COMPLETED,
        {"block_count": len(context_result.output.blocks)},
    )
    _append(event_writer, run_id, task_id, "stopped", RUN_COMPLETED, {"ok": True})
    return context_result


def _append(
    writer: EventWriter,
    run_id: str,
    task_id: str,
    phase: str,
    event_type: str,
    summary: dict[str, object],
) -> None:
    writer.append(
        RunEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            task_id=task_id,
            phase=phase,
            event_type=event_type,
            timestamp="",
            summary=summary,
            artifact_refs=(),
        )
    )


def _failed_context(result: CapabilityResult[object]) -> CapabilityResult[ContextPack]:
    return CapabilityResult(
        capability_name="context.build_readonly",
        ok=False,
        output=None,
        error=result.error,
        telemetry=result.telemetry,
        artifacts=result.artifacts,
    )


def _telemetry() -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=0,
        input_summary={},
        output_summary={},
        token_usage={},
        model_usage={},
        degraded=False,
        degradation_reason=None,
    )
