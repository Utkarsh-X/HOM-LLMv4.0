from dataclasses import dataclass
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import (
    EditProposalEvidenceContext,
    EditProposalRequest,
)
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, EvidenceCandidate, EvidenceRetrievalRequest, EvidenceSet
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)
from homllm_v4.planning.provider_edit_proposer import ProviderBackedEditProposer
from homllm_v4.planning.target_file_selector import (
    EvidenceTargetFileSelector,
    TargetFileSelectionRequest,
    TargetFileSelectionResult,
)
from homllm_v4.planning.target_section_scanner import scan_target_sections
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


@dataclass(frozen=True)
class ProviderProposedPatchPlanRequest:
    task_id: str
    workspace_root: str
    query: str
    task_class: str
    index_id: str
    target_file: str | None
    intent: str
    expected_behavior: str
    verification_argv: tuple[str, ...]
    retrieval_policy: dict[str, object]
    expected_content_hash: str | None = None
    repair_context: str = ""
    verification_timeout_seconds: int | None = None


class ProviderProposedPatchPlanner:
    def __init__(
        self,
        *,
        retrieval_service: EvidenceRetrievalService,
        direct_read_service: DirectReadService,
        edit_proposer: ProviderBackedEditProposer,
        evidence_planner: EvidenceBackedPatchPlanner | None = None,
        target_selector: EvidenceTargetFileSelector | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.direct_read_service = direct_read_service
        self.edit_proposer = edit_proposer
        self.evidence_planner = evidence_planner or EvidenceBackedPatchPlanner()
        self.target_selector = target_selector or EvidenceTargetFileSelector()

    def plan(
        self,
        request: ProviderProposedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        retrieval = self.retrieval_service.retrieve(
            EvidenceRetrievalRequest(
                task_id=request.task_id,
                query=request.query,
                task_class=request.task_class,
                index_id=request.index_id,
                policy=request.retrieval_policy,
                target_files=(request.target_file,) if request.target_file else (),
            )
        )
        if not retrieval.ok or retrieval.output is None:
            return retrieval

        selection: TargetFileSelectionResult | None = None
        target_file = request.target_file
        if target_file is None:
            selection = self.target_selector.select(
                TargetFileSelectionRequest(
                    task_id=request.task_id,
                    evidence_set=retrieval.output,
                )
            )
            if selection.decision != "selected" or selection.target_file is None:
                return _target_selection_failed(request, selection)
            target_file = selection.target_file

        direct_read = self.direct_read_service.read(
            DirectReadRequest(
                task_id=request.task_id,
                file_path=target_file,
                require_hash=True,
            )
        )
        if not direct_read.ok or direct_read.output is None:
            return direct_read

        # Check if the evidence set has any candidate matching the target file.
        # If not, synthesize a fallback candidate from the direct read so the
        # edit can still proceed -- but surface the retrieval miss in
        # telemetry, because a fallback means the model never saw retrieved
        # evidence for the file it must edit.
        has_evidence_for_target = any(
            candidate.file_path == target_file
            for candidate in retrieval.output.candidates
        )
        target_file_retrieval_score = _best_retrieval_score(
            retrieval.output.candidates,
            target_file,
        )
        if not has_evidence_for_target:
            fallback_candidates = _target_section_fallback_candidates(
                target_file=target_file,
                content=direct_read.output.content_excerpt or "",
                query=request.query,
                context=" ".join((request.intent, request.expected_behavior)),
                full_content_hash=direct_read.output.content_hash or "",
            )
            evidence_set = EvidenceSet(
                evidence_set_id=retrieval.output.evidence_set_id,
                query=retrieval.output.query,
                candidates=retrieval.output.candidates + fallback_candidates,
                diagnostics=retrieval.output.diagnostics,
            )
        else:
            evidence_set = retrieval.output

        proposal = self.edit_proposer.propose(
            EditProposalRequest(
                task_id=request.task_id,
                target_file=target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                current_content=direct_read.output.content_excerpt,
                evidence_ids=tuple(
                    candidate.candidate_id
                    for candidate in evidence_set.candidates
                    if candidate.file_path == target_file
                ),
                allowed_file_paths=(target_file,),
                verification_summary=" ".join(request.verification_argv),
                evidence_context=_evidence_context_for_target(
                    evidence_set,
                    target_file,
                ),
                repair_context=request.repair_context,
            )
        )
        if not proposal.ok or proposal.output is None:
            return proposal
        provider_prompt_metrics = _provider_prompt_metrics(proposal.telemetry.output_summary)
        provider_token_usage = proposal.telemetry.token_usage if proposal.telemetry else {}
        provider_model_usage = proposal.telemetry.model_usage if proposal.telemetry else {}

        planned = self.evidence_planner.plan(
            EvidenceBackedPatchPlanRequest(
                task_id=request.task_id,
                workspace_root=str(Path(request.workspace_root)),
                target_file=proposal.output.target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                evidence_set=evidence_set,
                direct_reads=(direct_read.output,),
                expected_content_hash=request.expected_content_hash,
                new_content=_preserve_original_trailing_newline(
                    proposal.output.new_content,
                    direct_read.output.content_excerpt,
                ),
                verification_argv=request.verification_argv,
                allowed_file_paths=(target_file,),
                verification_timeout_seconds=request.verification_timeout_seconds,
            )
        )
        return _with_provider_planner_telemetry(
            planned,
            request=request,
            resolved_target_file=target_file,
            selection=selection,
            provider_prompt_metrics=provider_prompt_metrics,
            provider_token_usage=provider_token_usage,
            provider_model_usage=provider_model_usage,
            target_evidence_retrieved=has_evidence_for_target,
            target_file_retrieval_score=target_file_retrieval_score,
            retrieved_evidence_count=len(retrieval.output.candidates),
        )


def _target_section_fallback_candidates(
    *,
    target_file: str,
    content: str,
    query: str,
    context: str,
    full_content_hash: str,
) -> tuple[EvidenceCandidate, ...]:
    """Build target-file evidence from a section scan when retrieval missed it.

    The previous fallback was a single candidate holding the *entire* file,
    which the evidence renderer truncated to its first ~2000 chars (the
    import header). Instead, scan the file for query-relevant sections and
    emit each as a candidate with a real line span, so the model sees e.g.
    ``[target-section-1] complexes.py:400-479`` with actual code rather than
    a useless header. Falls back to the old full-file candidate only when the
    scan finds nothing (e.g. no query token appears in the file).
    """
    sections = scan_target_sections(
        content,
        query=query,
        context=context,
    )
    if sections:
        return tuple(
            EvidenceCandidate(
                candidate_id=f"target-section-{index}",
                file_path=target_file,
                symbol_id=None,
                span_start=section.span_start,
                span_end=section.span_end,
                content_hash=_hash_text(section.content),
                source_channels=("target_section_scan",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=float(section.score),
                metadata={
                    "content": section.content,
                    "target_section_scan": True,
                    "section_score": section.score,
                },
            )
            for index, section in enumerate(sections)
        )
    safe_target = target_file.replace('/', '_').replace('\\', '_').replace('.', '_')
    return (
        EvidenceCandidate(
            candidate_id=f"fallback-{safe_target}",
            file_path=target_file,
            symbol_id=None,
            span_start=1,
            span_end=None,
            content_hash=full_content_hash,
            source_channels=("direct_read_fallback",),
            bm25_score=1.0,
            vector_score=None,
            graph_score=None,
            retrieval_score=1.0,
            metadata={"content": content},
        ),
    )


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _best_retrieval_score(
    candidates: tuple[EvidenceCandidate, ...],
    target_file: str,
) -> float | None:
    scores = [
        candidate.retrieval_score
        for candidate in candidates
        if candidate.file_path == target_file and candidate.retrieval_score is not None
    ]
    if not scores:
        return None
    return max(scores)


def _preserve_original_trailing_newline(new_content: str, old_content: str) -> str:
    if old_content.endswith("\n") and not new_content.endswith("\n"):
        return f"{new_content}\n"
    return new_content


def _evidence_context_for_target(
    evidence_set: EvidenceSet,
    target_file: str,
) -> tuple[EditProposalEvidenceContext, ...]:
    return tuple(
        EditProposalEvidenceContext(
            evidence_id=candidate.candidate_id,
            file_path=candidate.file_path,
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            content=str(candidate.metadata.get("content") or ""),
        )
        for candidate in evidence_set.candidates
        if candidate.file_path == target_file
    )


def _target_selection_failed(
    request: ProviderProposedPatchPlanRequest,
    selection: TargetFileSelectionResult,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    code = (
        "target_selection_ambiguous"
        if selection.decision == "ambiguous"
        else "target_selection_failed"
    )
    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=False,
        output=None,
        error=CapabilityError(
            code=code,
            message=selection.reason or "target file selection failed",
            recoverable=True,
            retryable=False,
            details={
                "decision": selection.decision,
                "candidate_file_scores": selection.candidate_file_scores,
            },
        ),
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=0,
            input_summary={"task_id": request.task_id},
            output_summary={
                "selection_decision": selection.decision,
                "selection_reason": selection.reason,
            },
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        ),
        artifacts=(),
    )


def _with_provider_planner_telemetry(
    result: CapabilityResult[EvidenceBackedPatchPlanResult],
    *,
    request: ProviderProposedPatchPlanRequest,
    resolved_target_file: str,
    selection: TargetFileSelectionResult | None,
    provider_prompt_metrics: dict[str, object],
    provider_token_usage: dict[str, int],
    provider_model_usage: dict[str, object],
    target_evidence_retrieved: bool | None = None,
    target_file_retrieval_score: float | None = None,
    retrieved_evidence_count: int | None = None,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    output_summary = dict(result.telemetry.output_summary)
    output_summary.update(provider_prompt_metrics)
    output_summary["resolved_target_file"] = resolved_target_file
    if target_evidence_retrieved is not None:
        output_summary["target_evidence_retrieved"] = target_evidence_retrieved
    if target_file_retrieval_score is not None:
        output_summary["target_file_retrieval_score"] = target_file_retrieval_score
    if retrieved_evidence_count is not None:
        output_summary["retrieved_evidence_count"] = retrieved_evidence_count
    if selection is None:
        output_summary["target_selection_decision"] = "supplied"
    else:
        output_summary["target_selection_decision"] = selection.decision
        output_summary["candidate_file_scores"] = selection.candidate_file_scores
        output_summary["target_selection_confidence"] = selection.confidence

    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=result.telemetry.duration_ms,
            input_summary={
                "task_id": request.task_id,
                "target_file_supplied": request.target_file is not None,
            },
            output_summary=output_summary,
            token_usage=provider_token_usage,
            model_usage=provider_model_usage,
            degraded=result.telemetry.degraded,
            degradation_reason=result.telemetry.degradation_reason,
        ),
        artifacts=result.artifacts,
    )


def _provider_prompt_metrics(output_summary: dict[str, object]) -> dict[str, object]:
    metrics: dict[str, object] = {}
    for key in (
        "prompt_char_count",
        "evidence_context_item_count",
        "evidence_context_rendered_char_count",
        "evidence_context_truncated",
        "current_content_char_count",
        "current_content_truncated",
    ):
        if key in output_summary:
            metrics[key] = output_summary[key]
    return metrics
