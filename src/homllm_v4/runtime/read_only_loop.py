from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextPack, ContextPackRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import EvidenceRetrievalRequest
from homllm_v4.contracts.index import IndexRequest
from homllm_v4.contracts.loop import (
    ClaimSupport,
    LoopPassRecord,
    ReadOnlyLoopRequest,
    ReadOnlyLoopResult,
    SufficiencyDecision,
)
from homllm_v4.contracts.policy import CapabilityPolicy
from homllm_v4.contracts.ranking import EvidenceRankingRequest
from homllm_v4.ledger.events import (
    CONTEXT_COMPLETED,
    INDEX_VALIDATED,
    LOOP_PASS_STARTED,
    POLICY_CREATED,
    RANKING_COMPLETED,
    REPEATED_STATE_DETECTED,
    RETRIEVAL_COMPLETED,
    RUN_COMPLETED,
    RUN_STARTED,
    SERVICE_FAILED,
    SUFFICIENCY_DECIDED,
    RunEvent,
)
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.runtime.repetition_guard import is_repeated_retrieval
from homllm_v4.runtime.sufficiency import (
    DeterministicSufficiencyChecker,
    insufficient_decision,
)
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


class ReadOnlyMultipassLoop:
    def __init__(
        self,
        *,
        service_registry: ServiceRegistry,
        artifact_manager: ArtifactManager,
        event_writer: EventWriter,
        policy: CapabilityPolicy,
        sufficiency_checker: DeterministicSufficiencyChecker | None = None,
    ) -> None:
        self.service_registry = service_registry
        self.artifact_manager = artifact_manager
        self.event_writer = event_writer
        self.policy = policy
        self.sufficiency_checker = sufficiency_checker or DeterministicSufficiencyChecker()

    def run(self, request: ReadOnlyLoopRequest) -> ReadOnlyLoopResult:
        self._append(request, "created", RUN_STARTED, {"query": request.query})
        self._append(
            request,
            "policy",
            POLICY_CREATED,
            {"permission_profile": self.policy.permission_profile},
        )

        index_result = self._validate_index(request)
        if not index_result.ok:
            return self._service_failed_result(request, index_result.error)
        self._append(request, "index", INDEX_VALIDATED, {"ok": True})

        passes: list[LoopPassRecord] = []
        previous_sufficiency: SufficiencyDecision | None = None

        for pass_index in range(1, max(1, request.max_passes) + 1):
            self._append(
                request,
                "retrieval",
                LOOP_PASS_STARTED,
                {"pass_index": pass_index},
            )
            pass_result = self._run_pass(request, pass_index)
            if isinstance(pass_result, CapabilityError):
                return self._service_failed_result(request, pass_result, tuple(passes))

            passes.append(pass_result)
            self._append(
                request,
                "sufficiency",
                SUFFICIENCY_DECIDED,
                {
                    "pass_index": pass_index,
                    "sufficient": pass_result.sufficiency.sufficient,
                    "score": pass_result.sufficiency.score,
                    "missing": list(pass_result.sufficiency.missing_reasons),
                },
            )

            if pass_result.sufficiency.sufficient:
                return self._completed_result(request, "sufficient", tuple(passes))

            if not pass_result.evidence_set.candidates:
                return self._completed_result(request, "empty_evidence", tuple(passes))

            if len(passes) >= 2 and previous_sufficiency is not None:
                if is_repeated_retrieval(
                    passes[-2].evidence_set,
                    passes[-1].evidence_set,
                    previous_sufficiency_score=previous_sufficiency.score,
                    current_sufficiency_score=pass_result.sufficiency.score,
                ):
                    self._append(
                        request,
                        "repetition",
                        REPEATED_STATE_DETECTED,
                        {"pass_index": pass_index},
                    )
                    return self._completed_result(
                        request,
                        "repeated_state",
                        tuple(passes),
                    )

            previous_sufficiency = pass_result.sufficiency

        return self._completed_result(request, "budget_exhausted", tuple(passes))

    def _validate_index(
        self,
        request: ReadOnlyLoopRequest,
    ) -> CapabilityResult[object]:
        service = self.service_registry.get("index.validate", IndexService)
        return service.validate(
            IndexRequest(
                workspace_root=request.workspace_root,
                include_patterns=("**/*.py",),
                exclude_patterns=(".git/**", ".homllm/**"),
                language_profile="python",
                mode="validate",
                artifact_paths=request.index_artifact_paths or {},
            )
        )

    def _run_pass(
        self,
        request: ReadOnlyLoopRequest,
        pass_index: int,
    ) -> LoopPassRecord | CapabilityError:
        retrieval_service = self.service_registry.get(
            "evidence.retrieve",
            EvidenceRetrievalService,
        )
        retrieval_result = retrieval_service.retrieve(
            EvidenceRetrievalRequest(
                task_id=request.task_id,
                query=request.query,
                task_class="answer",
                index_id="idx",
                policy={"top_k": 50 + ((pass_index - 1) * 10)},
            )
        )
        if not retrieval_result.ok:
            self._append_service_failed(request, "evidence.retrieve")
            return retrieval_result.error
        self._append(
            request,
            "retrieval",
            RETRIEVAL_COMPLETED,
            {
                "pass_index": pass_index,
                "candidate_count": len(retrieval_result.output.candidates),
            },
        )

        ranking_service = self.service_registry.get("evidence.rank", EvidenceRankingService)
        ranking_result = ranking_service.rank(
            EvidenceRankingRequest(
                task_id=request.task_id,
                evidence_set=retrieval_result.output,
                policy={},
            )
        )
        if not ranking_result.ok:
            self._append_service_failed(request, "evidence.rank")
            return ranking_result.error
        self._append(
            request,
            "ranking",
            RANKING_COMPLETED,
            {"pass_index": pass_index, "item_count": len(ranking_result.output.items)},
        )

        context_service = self.service_registry.get("context.build", ContextPackService)
        context_result = context_service.build(
            ContextPackRequest(
                task_id=request.task_id,
                ranked_evidence_set=ranking_result.output,
                policy={},
                query=request.query,
            )
        )
        if not context_result.ok:
            self._append_service_failed(request, "context.build")
            return context_result.error
        self._append(
            request,
            "context",
            CONTEXT_COMPLETED,
            {"pass_index": pass_index, "block_count": len(context_result.output.blocks)},
        )

        sufficiency = self.sufficiency_checker.check(
            evidence_set=retrieval_result.output,
            context_pack=context_result.output,
            min_candidates=request.min_candidates,
            min_context_blocks=request.min_context_blocks,
        )
        return LoopPassRecord(
            pass_index=pass_index,
            evidence_set=retrieval_result.output,
            ranked_evidence_set=ranking_result.output,
            context_pack=context_result.output,
            sufficiency=sufficiency,
        )

    def _completed_result(
        self,
        request: ReadOnlyLoopRequest,
        stop_reason,
        passes: tuple[LoopPassRecord, ...],
    ) -> ReadOnlyLoopResult:
        last_pass = passes[-1] if passes else None
        context_pack = last_pass.context_pack if last_pass else None
        sufficiency = (
            last_pass.sufficiency
            if last_pass
            else insufficient_decision(str(stop_reason))
        )
        claim_support = self._build_claim_support(context_pack)
        response_text = self._compose_response(context_pack, claim_support, stop_reason)
        self._append(
            request,
            "stopped",
            RUN_COMPLETED,
            {"stop_reason": stop_reason, "pass_count": len(passes)},
        )
        result = ReadOnlyLoopResult(
            task_id=request.task_id,
            run_id=request.run_id,
            stop_reason=stop_reason,
            pass_count=len(passes),
            sufficiency=sufficiency,
            passes=passes,
            context_pack=context_pack,
            response_text=response_text,
            claim_support=claim_support,
            error=None,
        )
        self._persist_result(result)
        return result

    def _service_failed_result(
        self,
        request: ReadOnlyLoopRequest,
        error: CapabilityError | None,
        passes: tuple[LoopPassRecord, ...] = (),
    ) -> ReadOnlyLoopResult:
        self._append_service_failed(
            request,
            str(error.code if error else "unknown_service"),
        )
        self._append(
            request,
            "stopped",
            RUN_COMPLETED,
            {"stop_reason": "service_failed", "pass_count": len(passes)},
        )
        result = ReadOnlyLoopResult(
            task_id=request.task_id,
            run_id=request.run_id,
            stop_reason="service_failed",
            pass_count=len(passes),
            sufficiency=insufficient_decision("service_failed"),
            passes=passes,
            context_pack=None,
            response_text="Read-only loop stopped because a required service failed.",
            claim_support=(),
            error=error,
        )
        self._persist_result(result)
        return result

    def _persist_result(self, result: ReadOnlyLoopResult) -> None:
        self.artifact_manager.write_json(
            "response/read_only_loop_result.json",
            result,
            "response",
            "read-only loop result",
        )

    @staticmethod
    def _build_claim_support(context_pack: ContextPack | None) -> tuple[ClaimSupport, ...]:
        if context_pack is None:
            return ()
        return tuple(
            ClaimSupport(
                claim_id=f"claim-{index}",
                claim_text=f"Relevant evidence is available in {block.citation}.",
                evidence_ids=(block.candidate_id,),
            )
            for index, block in enumerate(context_pack.blocks, start=1)
        )

    @staticmethod
    def _compose_response(
        context_pack: ContextPack | None,
        claim_support: tuple[ClaimSupport, ...],
        stop_reason: str,
    ) -> str:
        if context_pack is None:
            return f"Read-only loop stopped with reason: {stop_reason}."
        return (
            "Evidence-backed context is ready. "
            f"Stop reason: {stop_reason}. "
            f"Supported claims: {len(claim_support)}. "
            f"Context blocks: {len(context_pack.blocks)}."
        )

    def _append_service_failed(self, request: ReadOnlyLoopRequest, service: str) -> None:
        self._append(
            request,
            "error",
            SERVICE_FAILED,
            {"service": service},
        )

    def _append(
        self,
        request: ReadOnlyLoopRequest,
        phase: str,
        event_type: str,
        summary: dict[str, object],
    ) -> None:
        self.event_writer.append(
            RunEvent(
                event_id=str(uuid4()),
                run_id=request.run_id,
                task_id=request.task_id,
                phase=phase,
                event_type=event_type,
                timestamp="",
                summary=summary,
                artifact_refs=(),
            )
        )
