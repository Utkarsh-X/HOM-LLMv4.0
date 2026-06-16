from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.context import ContextBlock, ContextPack
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.runtime.grounded_answer import (
    GroundedAnswerRequest,
    GroundedAnswerSynthesizer,
)


class RecordingAnswerProvider:
    def __init__(
        self,
        *,
        text: str = "normalize_sku is implemented in inventory/items.py [inventory/items.py:1-2].",
        tokens_in: int = 123,
        tokens_out: int = 17,
        model: str = "fake-answer-model",
        fail: Exception | None = None,
    ) -> None:
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.model = model
        self.fail = fail
        self.requests: list[ProviderEditProposalRequest] = []

    def propose_edit(
        self,
        request: ProviderEditProposalRequest,
    ) -> ProviderEditProposalResponse:
        self.requests.append(request)
        if self.fail is not None:
            raise self.fail
        return ProviderEditProposalResponse(
            text=self.text,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            model=self.model,
            metadata={"finish_reason": "stop"},
        )


def context_pack() -> ContextPack:
    return ContextPack(
        context_pack_id="ctx-1",
        purpose="answer",
        text="",
        blocks=(
            ContextBlock(
                block_id="block-1",
                candidate_id="ev-1",
                file_path="inventory/items.py",
                span_start=1,
                span_end=2,
                text="def normalize_sku(sku: str) -> str:\n    return sku.upper()",
                token_count=14,
                score=0.9,
                citation="inventory/items.py:1-2",
            ),
            ContextBlock(
                block_id="block-2",
                candidate_id="ev-2",
                file_path="README.md",
                span_start=5,
                span_end=7,
                text="Inventory helpers normalize SKU values.",
                token_count=8,
                score=0.7,
                citation="README.md:5-7",
            ),
        ),
        used_tokens=22,
        dropped_candidates=(),
        diagnostics={},
    )


def test_grounded_answer_synthesizer_uses_context_and_writes_artifacts(tmp_path: Path) -> None:
    provider = RecordingAnswerProvider()
    artifacts = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / "runs")
    artifacts.create_run("answer-run", {"entrypoint": "test"})

    result = GroundedAnswerSynthesizer(
        provider=provider,
        artifact_manager=artifacts,
        max_prompt_chars=5000,
    ).synthesize(
        GroundedAnswerRequest(
            task_id="answer-run",
            query="Where is normalize_sku implemented?",
            context_pack=context_pack(),
        )
    )

    assert result.ok is True
    assert result.answer_text == provider.text
    assert result.error_code is None
    assert result.metrics["provider_tokens_in"] == 123
    assert result.metrics["provider_tokens_out"] == 17
    assert result.metrics["provider_model"] == "fake-answer-model"
    assert len(provider.requests) == 1
    assert provider.requests[0].response_format == "text"
    assert "Where is normalize_sku implemented?" in provider.requests[0].prompt
    assert "[inventory/items.py:1-2]" in provider.requests[0].prompt
    assert "[README.md:5-7]" in provider.requests[0].prompt
    assert "inventory/items.py:1-2" in provider.requests[0].prompt
    assert "README.md:5-7" in provider.requests[0].prompt
    assert "return sku.upper()" in provider.requests[0].prompt
    assert (tmp_path / "runs" / "answer-run" / "provider" / "answer-run" / "prompt.txt").is_file()
    assert (tmp_path / "runs" / "answer-run" / "provider" / "answer-run" / "response.txt").is_file()


def test_grounded_answer_synthesizer_requires_context_before_provider_call() -> None:
    provider = RecordingAnswerProvider()

    result = GroundedAnswerSynthesizer(provider=provider).synthesize(
        GroundedAnswerRequest(
            task_id="answer-run",
            query="Where is normalize_sku implemented?",
            context_pack=None,
        )
    )

    assert result.ok is False
    assert result.answer_text == ""
    assert result.error_code == "answer_context_missing"
    assert provider.requests == []


def test_grounded_answer_synthesizer_enforces_prompt_budget_before_provider_call() -> None:
    provider = RecordingAnswerProvider()

    result = GroundedAnswerSynthesizer(
        provider=provider,
        max_prompt_chars=10,
    ).synthesize(
        GroundedAnswerRequest(
            task_id="answer-run",
            query="Where is normalize_sku implemented?",
            context_pack=context_pack(),
        )
    )

    assert result.ok is False
    assert result.error_code == "answer_prompt_budget_exceeded"
    assert provider.requests == []
    assert result.metrics["prompt_char_count"] > 10


def test_grounded_answer_synthesizer_reports_provider_invocation_failure() -> None:
    provider = RecordingAnswerProvider(fail=RuntimeError("network denied"))

    result = GroundedAnswerSynthesizer(provider=provider).synthesize(
        GroundedAnswerRequest(
            task_id="answer-run",
            query="Where is normalize_sku implemented?",
            context_pack=context_pack(),
        )
    )

    assert result.ok is False
    assert result.error_code == "answer_provider_invocation_failed"
    assert result.answer_text == ""
    assert len(provider.requests) == 1


def test_grounded_answer_synthesizer_rejects_blank_provider_response() -> None:
    provider = RecordingAnswerProvider(text=" \n\t")

    result = GroundedAnswerSynthesizer(provider=provider).synthesize(
        GroundedAnswerRequest(
            task_id="answer-run",
            query="Where is normalize_sku implemented?",
            context_pack=context_pack(),
        )
    )

    assert result.ok is False
    assert result.error_code == "answer_provider_empty_response"
    assert result.answer_text == ""
