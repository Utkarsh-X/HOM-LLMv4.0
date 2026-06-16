from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import EditProposalRequest, EditProposalResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.bounded_edit_proposer import BoundedEditProposer


@dataclass(frozen=True)
class ProviderEditProposalRequest:
    task_id: str
    prompt: str
    response_format: str = "json"


@dataclass(frozen=True)
class ProviderEditProposalResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = "unknown"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _EvidenceContextRender:
    text: str
    item_count: int
    rendered_char_count: int
    truncated: bool


@dataclass(frozen=True)
class _PromptBuild:
    prompt: str
    prompt_char_count: int
    evidence_context_item_count: int
    evidence_context_rendered_char_count: int
    evidence_context_truncated: bool


class EditProposalProvider(Protocol):
    def propose_edit(
        self,
        request: ProviderEditProposalRequest,
    ) -> ProviderEditProposalResponse:
        ...


class ProviderBackedEditProposer:
    def __init__(
        self,
        *,
        provider: EditProposalProvider,
        artifact_manager: ArtifactManager | None = None,
        max_evidence_item_chars: int = 2000,
        max_evidence_context_chars: int = 12000,
        max_prompt_chars: int | None = None,
    ) -> None:
        self.provider = provider
        self.artifact_manager = artifact_manager
        self.max_evidence_item_chars = max(1, int(max_evidence_item_chars))
        self.max_evidence_context_chars = max(1, int(max_evidence_context_chars))
        self.max_prompt_chars = None if max_prompt_chars is None else max(1, int(max_prompt_chars))

    def propose(self, request: EditProposalRequest) -> CapabilityResult[EditProposalResult]:
        started = perf_counter()
        provider_response: ProviderEditProposalResponse | None = None
        prompt_build = _build_edit_proposal_prompt_with_metadata(
            request,
            max_evidence_item_chars=self.max_evidence_item_chars,
            max_evidence_context_chars=self.max_evidence_context_chars,
        )
        prompt = prompt_build.prompt
        artifacts = self._write_prompt_artifact(request, prompt)
        if (
            self.max_prompt_chars is not None
            and prompt_build.prompt_char_count > self.max_prompt_chars
        ):
            return _failed(
                request=request,
                started=started,
                provider_response=None,
                prompt_build=prompt_build,
                code="provider_prompt_budget_exceeded",
                message="provider prompt exceeds configured maximum size",
                details={
                    "prompt_char_count": prompt_build.prompt_char_count,
                    "max_prompt_chars": self.max_prompt_chars,
                },
                artifacts=artifacts,
            )

        try:
            provider_response = self.provider.propose_edit(
                ProviderEditProposalRequest(
                    task_id=request.task_id,
                    prompt=prompt,
                )
            )
        except Exception as exc:
            return _failed(
                request=request,
                started=started,
                provider_response=None,
                prompt_build=prompt_build,
                code="provider_invocation_failed",
                message=str(exc),
                details=None,
                artifacts=artifacts,
            )

        artifacts += self._write_response_artifact(request, provider_response.text)
        try:
            proposal = parse_provider_edit_response(provider_response.text)
        except Exception as exc:
            finish_reason = str(
                getattr(provider_response, "metadata", {}).get("finish_reason", "")
            ).lower()
            if finish_reason in {"max_tokens", "length"}:
                code = "provider_response_truncated"
                details = {"finish_reason": finish_reason}
            else:
                code = "provider_response_invalid"
                details = None
            return _failed(
                request=request,
                started=started,
                provider_response=provider_response,
                prompt_build=prompt_build,
                code=code,
                message=str(exc),
                details=details,
                artifacts=artifacts,
            )

        unknown_evidence = tuple(sorted(set(proposal.evidence_ids) - set(request.evidence_ids)))
        if unknown_evidence:
            return _failed(
                request=request,
                started=started,
                provider_response=provider_response,
                prompt_build=prompt_build,
                code="proposal_evidence_scope_denied",
                message="proposal references evidence ids outside the request",
                details={"unknown_evidence_ids": unknown_evidence},
                artifacts=artifacts,
            )

        bounded = BoundedEditProposer(proposer=lambda _: proposal).propose(request)
        return _with_provider_usage(
            bounded,
            started=started,
            provider_response=provider_response,
            prompt_build=prompt_build,
            request=request,
            artifacts=artifacts,
        )

    def _write_prompt_artifact(
        self,
        request: EditProposalRequest,
        prompt: str,
    ) -> tuple[ArtifactRef, ...]:
        if self.artifact_manager is None:
            return ()
        return (
            self.artifact_manager.write_text(
                f"provider/{_safe_segment(request.task_id)}/prompt.txt",
                prompt,
                "provider_prompt",
                "provider edit proposal prompt",
            ),
        )

    def _write_response_artifact(
        self,
        request: EditProposalRequest,
        response_text: str,
    ) -> tuple[ArtifactRef, ...]:
        if self.artifact_manager is None:
            return ()
        return (
            self.artifact_manager.write_text(
                f"provider/{_safe_segment(request.task_id)}/response.txt",
                response_text,
                "provider_response",
                "provider edit proposal raw response",
            ),
        )


def build_edit_proposal_prompt(
    request: EditProposalRequest,
    *,
    max_evidence_item_chars: int = 2000,
    max_evidence_context_chars: int = 12000,
) -> str:
    return _build_edit_proposal_prompt_with_metadata(
        request,
        max_evidence_item_chars=max_evidence_item_chars,
        max_evidence_context_chars=max_evidence_context_chars,
    ).prompt


def _build_edit_proposal_prompt_with_metadata(
    request: EditProposalRequest,
    *,
    max_evidence_item_chars: int,
    max_evidence_context_chars: int,
) -> _PromptBuild:
    evidence_render = _render_evidence_context(
        request,
        max_evidence_item_chars=max_evidence_item_chars,
        max_evidence_context_chars=max_evidence_context_chars,
    )
    prompt = "\n".join(
        (
            "You are proposing a bounded single-file edit.",
            "Return only JSON with keys: target_file, new_content, rationale, evidence_ids, risk_flags.",
            "new_content must be the complete replacement content for the entire target file.",
            "new_content must be a valid JSON string with escaped newlines and quotes.",
            "After JSON parsing, new_content must be normal source text with normal quotes.",
            "Do not include literal backslash-escaped quote characters in source code unless they already exist.",
            "Do not return a snippet, diff, patch, or partial function body.",
            "Do not use Python triple-quoted strings for new_content.",
            "For no-op or validation-only tasks, return current content unchanged.",
            "Exact examples in Expected behavior are mandatory acceptance criteria.",
            "The proposed new_content must satisfy the Verification command.",
            "Do not use a plausible generic fix if it violates an exact expected output.",
            "Do not call a helper that re-acquires a non-reentrant lock while inside that lock.",
            "Do not modify files outside the allowed file list.",
            "Do not cite evidence ids that are not listed in this request.",
            f"Task ID: {request.task_id}",
            f"Target file: {request.target_file}",
            f"Allowed files: {', '.join(request.allowed_file_paths)}",
            f"Intent: {request.intent}",
            f"Expected behavior: {request.expected_behavior}",
            *(("Repair context: " + request.repair_context,) if request.repair_context else ()),
            f"Evidence IDs: {', '.join(request.evidence_ids)}",
            f"Verification: {request.verification_summary}",
            evidence_render.text,
            "Current content:",
            request.current_content,
        )
    )
    return _PromptBuild(
        prompt=prompt,
        prompt_char_count=len(prompt),
        evidence_context_item_count=evidence_render.item_count,
        evidence_context_rendered_char_count=evidence_render.rendered_char_count,
        evidence_context_truncated=evidence_render.truncated,
    )


def _render_evidence_context(
    request: EditProposalRequest,
    *,
    max_evidence_item_chars: int,
    max_evidence_context_chars: int,
) -> _EvidenceContextRender:
    if not request.evidence_context:
        return _EvidenceContextRender(
            text="Evidence context: none supplied",
            item_count=0,
            rendered_char_count=0,
            truncated=False,
        )
    item_limit = max(1, int(max_evidence_item_chars))
    remaining = max(1, int(max_evidence_context_chars))
    lines = ["Evidence context:"]
    rendered_char_count = 0
    truncated = False
    last_index = len(request.evidence_context) - 1
    for index, item in enumerate(request.evidence_context):
        if remaining <= 0:
            lines.append("[evidence context budget exhausted]")
            truncated = True
            break
        content = item.content[: min(item_limit, remaining)]
        was_truncated = len(content) < len(item.content)
        truncated = truncated or was_truncated
        lines.append(
            f"[{item.evidence_id}] "
            f"{_format_location(item.file_path, item.span_start, item.span_end)}"
        )
        lines.append(content)
        rendered_char_count += len(content)
        if was_truncated:
            lines.append("[truncated]")
        remaining -= len(content)
        if remaining <= 0 and index != last_index:
            lines.append("[evidence context budget exhausted]")
            truncated = True
            break
    return _EvidenceContextRender(
        text="\n".join(lines),
        item_count=len(request.evidence_context),
        rendered_char_count=rendered_char_count,
        truncated=truncated,
    )


def _format_location(file_path: str, span_start: int | None, span_end: int | None) -> str:
    if span_start is None and span_end is None:
        return file_path
    if span_start is not None and span_end is not None:
        return f"{file_path}:{span_start}-{span_end}"
    if span_start is not None:
        return f"{file_path}:{span_start}"
    return f"{file_path}:?-{span_end}"


def parse_provider_edit_response(text: str) -> EditProposalResult:
    data = json.loads(_json_text_from_provider_response(text))
    if not isinstance(data, dict):
        raise ValueError("provider response must be a JSON object")

    required = ("target_file", "new_content", "rationale", "evidence_ids", "risk_flags")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"provider response missing keys: {', '.join(missing)}")

    if not isinstance(data["evidence_ids"], list):
        raise ValueError("provider response evidence_ids must be a list")
    if not isinstance(data["risk_flags"], list):
        raise ValueError("provider response risk_flags must be a list")

    return EditProposalResult(
        target_file=_string_field(data, "target_file"),
        new_content=_string_field(data, "new_content"),
        rationale=_string_field(data, "rationale"),
        evidence_ids=tuple(str(item) for item in data["evidence_ids"]),
        risk_flags=tuple(str(item) for item in data["risk_flags"]),
    )


def _json_text_from_provider_response(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _string_field(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"provider response {key} must be a string")
    return value


def _failed(
    *,
    request: EditProposalRequest,
    started: float,
    provider_response: ProviderEditProposalResponse | None,
    prompt_build: _PromptBuild,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    artifacts: tuple[ArtifactRef, ...] = (),
) -> CapabilityResult[EditProposalResult]:
    return CapabilityResult(
        capability_name="edit.propose.provider",
        ok=False,
        output=None,
        error=CapabilityError(
            code=code,
            message=message,
            recoverable=True,
            retryable=code == "provider_invocation_failed",
            details={"target_file": request.target_file, **(details or {})},
        ),
        telemetry=_telemetry(
            request=request,
            started=started,
            provider_response=provider_response,
            prompt_build=prompt_build,
            output_summary={"code": code},
        ),
        artifacts=artifacts,
    )


def _with_provider_usage(
    result: CapabilityResult[EditProposalResult],
    *,
    started: float,
    provider_response: ProviderEditProposalResponse,
    prompt_build: _PromptBuild,
    request: EditProposalRequest,
    artifacts: tuple[ArtifactRef, ...],
) -> CapabilityResult[EditProposalResult]:
    return CapabilityResult(
        capability_name="edit.propose.provider",
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=_telemetry(
            request=request,
            started=started,
            provider_response=provider_response,
            prompt_build=prompt_build,
            output_summary=result.telemetry.output_summary,
        ),
        artifacts=result.artifacts + artifacts,
    )


def _safe_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "task"


def _telemetry(
    *,
    request: EditProposalRequest,
    started: float,
    provider_response: ProviderEditProposalResponse | None,
    prompt_build: _PromptBuild,
    output_summary: dict[str, object],
) -> CapabilityTelemetry:
    token_usage: dict[str, int] = {}
    model_usage: dict[str, object] = {}
    if provider_response is not None:
        token_usage = {
            "input": provider_response.tokens_in,
            "output": provider_response.tokens_out,
        }
        model_usage = {"model": provider_response.model, **provider_response.metadata}

    enriched_output_summary = {
        **output_summary,
        "prompt_char_count": prompt_build.prompt_char_count,
        "evidence_context_item_count": prompt_build.evidence_context_item_count,
        "evidence_context_rendered_char_count": prompt_build.evidence_context_rendered_char_count,
        "evidence_context_truncated": prompt_build.evidence_context_truncated,
    }

    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=int((perf_counter() - started) * 1000),
        input_summary={
            "task_id": request.task_id,
            "target_file": request.target_file,
            "evidence_count": len(request.evidence_ids),
        },
        output_summary=enriched_output_summary,
        token_usage=token_usage,
        model_usage=model_usage,
        degraded=False,
        degradation_reason=None,
    )
