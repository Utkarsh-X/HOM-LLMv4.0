from dataclasses import dataclass, field
from pathlib import Path

import pytest

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import (
    DirectReadRequest,
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.agentic_patch_planner import AgenticLoopPatchPlanner
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.services.direct_read_service import DirectReadService


DIFF = (
    "--- a/config.py\n"
    "+++ b/config.py\n"
    "@@ -1,1 +1,1 @@\n"
    "-VALUE = 1\n"
    "+VALUE = 2\n"
)


@dataclass
class ScriptedProvider:
    responses: list[str]
    prompts: list[str] = field(default_factory=list)

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.prompts.append(request.prompt)
        return ProviderEditProposalResponse(
            text=self.responses.pop(0),
            tokens_in=321,
            tokens_out=123,
            model="scripted",
            metadata={"finish_reason": "stop"},
        )


@dataclass
class StubRetrievalService:
    evidence_set: EvidenceSet | None = None

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=self.evidence_set,
            error=None,
            telemetry=None,
            artifacts=(),
        )


def evidence_set_with_target() -> EvidenceSet:
    candidate = EvidenceCandidate(
        candidate_id="cand-1",
        file_path="config.py",
        symbol_id=None,
        span_start=1,
        span_end=1,
        content_hash="h",
        source_channels=("bm25",),
        bm25_score=1.0,
        vector_score=None,
        graph_score=None,
        retrieval_score=0.9,
        metadata={"content": "VALUE = 1\n"},
    )
    return EvidenceSet(
        evidence_set_id="set-1",
        query="value",
        candidates=(candidate,),
        diagnostics=RetrievalDiagnostics(
            bm25_count=1,
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )


def plan_request(tmp_path: Path, **overrides) -> ProviderProposedPatchPlanRequest:
    defaults = dict(
        task_id="task-1",
        workspace_root=str(tmp_path),
        query="bump value",
        task_class="mvp_agent_task",
        index_id="idx",
        target_file="config.py",
        intent="set VALUE to 2",
        expected_behavior="VALUE == 2",
        verification_argv=("python", "-c", "raise SystemExit(0)"),
        retrieval_policy={"intent": "PATCH", "top_k": 5},
    )
    defaults.update(overrides)
    return ProviderProposedPatchPlanRequest(**defaults)


def planner(provider, tmp_path: Path) -> AgenticLoopPatchPlanner:
    return AgenticLoopPatchPlanner(
        retrieval_service=StubRetrievalService(evidence_set=evidence_set_with_target()),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_provider=provider,
    )


def test_plan_produces_patch_request_from_loop_proposal(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = ScriptedProvider(
        responses=[
            '{"action": "propose_patch", "target_file": "config.py", "diff": '
            '"' + DIFF.replace("\n", "\\n") + '", "rationale": "r", "evidence_ids": ["cand-1"]}'
        ]
    )

    result = planner(provider, tmp_path).plan(plan_request(tmp_path))

    assert result.ok is True
    assert result.output is not None
    patch = result.output.patch_request.patches[0]
    assert patch.file_path == "config.py"
    assert patch.new_content == "VALUE = 2\n"
    assert result.telemetry is not None
    assert result.telemetry.output_summary["agent_stop_reason"] == "proposal_received"
    assert result.telemetry.output_summary["agent_turn_count"] == 1
    assert result.telemetry.token_usage == {"input": 321, "output": 123}


def test_seed_evidence_rendered_into_first_prompt(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = ScriptedProvider(
        responses=[
            '{"action": "propose_patch", "target_file": "config.py", "diff": '
            '"' + DIFF.replace("\n", "\\n") + '"}'
        ]
    )
    planner(provider, tmp_path).plan(plan_request(tmp_path))

    assert "[cand-1] config.py:1-1" in provider.prompts[0]


def test_finished_without_patch_is_retryable(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = ScriptedProvider(responses=['{"action": "finish", "rationale": "impossible"}'])

    result = planner(provider, tmp_path).plan(plan_request(tmp_path))

    assert result.ok is False
    assert result.error.code == "agent_finished_without_patch"
    assert result.error.retryable is True


def test_unappliable_diff_is_retryable(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    bad_diff = DIFF.replace("VALUE = 1", "ABSENT LINE")
    provider = ScriptedProvider(
        responses=[
            '{"action": "propose_patch", "target_file": "config.py", "diff": '
            '"' + bad_diff.replace("\n", "\\n") + '"}'
        ]
    )

    result = planner(provider, tmp_path).plan(plan_request(tmp_path))

    assert result.ok is False
    assert result.error.code == "provider_diff_not_applicable"
    assert result.error.retryable is True


def test_diff_against_changed_target_denied(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    denied_diff = DIFF.replace("config.py", "other.py")
    provider = ScriptedProvider(
        responses=[
            '{"action": "propose_patch", "target_file": "other.py", "diff": '
            '"' + denied_diff.replace("\n", "\\n") + '"}',
            '{"action": "propose_patch", "target_file": "config.py", "diff": '
            '"' + DIFF.replace("\n", "\\n") + '"}',
        ]
    )

    result = planner(provider, tmp_path).plan(plan_request(tmp_path))

    assert result.ok is True
    assert result.output.patch_request.patches[0].file_path == "config.py"
    loop_capability_telemetry = result.telemetry.output_summary
    assert loop_capability_telemetry["agent_turn_count"] == 2


def test_direct_read_used_for_hash_gate(tmp_path: Path) -> None:
    content = "VALUE = 1\r\n"
    (tmp_path / "config.py").write_text(content, encoding="utf-8")
    crlf_diff = (
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-VALUE = 1\n"
        "+VALUE = 2\n"
    )
    provider = ScriptedProvider(
        responses=[
            '{"action": "propose_patch", "target_file": "config.py", "diff": '
            '"' + crlf_diff.replace("\n", "\\n") + '"}'
        ]
    )

    result = planner(provider, tmp_path).plan(plan_request(tmp_path))

    assert result.ok is True
    patch = result.output.patch_request.patches[0]
    assert patch.new_content.replace("\r\n", "\n") == "VALUE = 2\n"
