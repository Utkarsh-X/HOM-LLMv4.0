from __future__ import annotations

import re
from dataclasses import dataclass, field

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.context import ContextPack
from homllm_v4.planning.provider_edit_proposer import (
    EditProposalProvider,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)


@dataclass(frozen=True)
class GroundedAnswerRequest:
    task_id: str
    query: str
    context_pack: ContextPack | None


@dataclass(frozen=True)
class GroundedAnswerResult:
    ok: bool
    answer_text: str
    error_code: str | None = None
    error_message: str | None = None
    metrics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _PromptBuild:
    prompt: str
    prompt_char_count: int
    context_block_count: int
    context_rendered_char_count: int


class GroundedAnswerSynthesizer:
    def __init__(
        self,
        *,
        provider: EditProposalProvider,
        artifact_manager: ArtifactManager | None = None,
        max_prompt_chars: int | None = None,
        max_context_block_chars: int = 2000,
    ) -> None:
        self.provider = provider
        self.artifact_manager = artifact_manager
        self.max_prompt_chars = None if max_prompt_chars is None else max(1, int(max_prompt_chars))
        self.max_context_block_chars = max(1, int(max_context_block_chars))

    def synthesize(self, request: GroundedAnswerRequest) -> GroundedAnswerResult:
        if request.context_pack is None or not request.context_pack.blocks:
            return GroundedAnswerResult(
                ok=False,
                answer_text="",
                error_code="answer_context_missing",
                error_message="grounded answer synthesis requires retrieved context",
                metrics={"context_block_count": 0},
            )

        prompt_build = self._build_prompt(request)
        artifacts_written = self._write_prompt_artifact(request, prompt_build.prompt)
        metrics: dict[str, object] = {
            "prompt_char_count": prompt_build.prompt_char_count,
            "context_block_count": prompt_build.context_block_count,
            "context_rendered_char_count": prompt_build.context_rendered_char_count,
            "artifact_count": artifacts_written,
        }
        if (
            self.max_prompt_chars is not None
            and prompt_build.prompt_char_count > self.max_prompt_chars
        ):
            metrics["max_prompt_chars"] = self.max_prompt_chars
            return GroundedAnswerResult(
                ok=False,
                answer_text="",
                error_code="answer_prompt_budget_exceeded",
                error_message="grounded answer prompt exceeds configured maximum size",
                metrics=metrics,
            )

        try:
            provider_response = self.provider.propose_edit(
                ProviderEditProposalRequest(
                    task_id=request.task_id,
                    prompt=prompt_build.prompt,
                    response_format="text",
                )
            )
        except Exception as exc:
            return GroundedAnswerResult(
                ok=False,
                answer_text="",
                error_code="answer_provider_invocation_failed",
                error_message=str(exc),
                metrics=metrics,
            )

        artifacts_written += self._write_response_artifact(
            request,
            provider_response.text,
        )
        answer_text = provider_response.text.strip()
        provider_metrics = _provider_metrics(provider_response)
        if not answer_text:
            return GroundedAnswerResult(
                ok=False,
                answer_text="",
                error_code="answer_provider_empty_response",
                error_message="grounded answer provider returned an empty response",
                metrics={**metrics, **provider_metrics, "artifact_count": artifacts_written},
            )

        return GroundedAnswerResult(
            ok=True,
            answer_text=answer_text,
            error_code=None,
            error_message=None,
            metrics={**metrics, **provider_metrics, "artifact_count": artifacts_written},
        )

    def _build_prompt(self, request: GroundedAnswerRequest) -> _PromptBuild:
        assert request.context_pack is not None
        context_lines = []
        rendered_char_count = 0
        for block in request.context_pack.blocks:
            text = block.text[: self.max_context_block_chars]
            rendered_char_count += len(text)
            context_lines.extend(
                (
                    f"[{block.citation}] evidence_id={block.candidate_id}",
                    text,
                )
            )
        prompt = "\n".join(
            (
                "You answer repository questions using only supplied repository context.",
                "If the context is insufficient, say what is missing instead of guessing.",
                "Cite files using the supplied citation labels.",
                "Keep the answer concise and directly useful to a developer.",
                f"Question: {request.query}",
                "Repository context:",
                "\n".join(context_lines),
            )
        )
        return _PromptBuild(
            prompt=prompt,
            prompt_char_count=len(prompt),
            context_block_count=len(request.context_pack.blocks),
            context_rendered_char_count=rendered_char_count,
        )

    def _write_prompt_artifact(
        self,
        request: GroundedAnswerRequest,
        prompt: str,
    ) -> int:
        if self.artifact_manager is None:
            return 0
        self.artifact_manager.write_text(
            f"provider/{_safe_segment(request.task_id)}/prompt.txt",
            prompt,
            "provider_answer_prompt",
            "provider grounded answer prompt",
        )
        return 1

    def _write_response_artifact(
        self,
        request: GroundedAnswerRequest,
        response_text: str,
    ) -> int:
        if self.artifact_manager is None:
            return 0
        self.artifact_manager.write_text(
            f"provider/{_safe_segment(request.task_id)}/response.txt",
            response_text,
            "provider_answer_response",
            "provider grounded answer raw response",
        )
        return 1


def _provider_metrics(response: ProviderEditProposalResponse) -> dict[str, object]:
    return {
        "provider_tokens_in": response.tokens_in,
        "provider_tokens_out": response.tokens_out,
        "provider_model": response.model,
        **{
            f"provider_{key}": value
            for key, value in response.metadata.items()
            if key not in {"tokens_in", "tokens_out", "model"}
        },
    }


def _safe_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "answer"
