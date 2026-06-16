import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from homllm_v4.adapters.v3_provider_patch_factory import build_v3_provider_proposed_patch_planner
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import (
    ProviderProposedPatchPlanRequest,
    ProviderProposedPatchPlanner,
)
from homllm_v4.registry.service_registry import ServiceRegistry


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class FakeRetrievalAdapter:
    def retrieve(self, request: EvidenceRetrievalRequest) -> EvidenceSet:
        content = "def add(a, b):\n    return a - b\n"
        return EvidenceSet(
            evidence_set_id="evidence-1",
            query=request.query,
            candidates=(
                EvidenceCandidate(
                    candidate_id="cand-1",
                    file_path="calculator.py",
                    symbol_id=None,
                    span_start=1,
                    span_end=2,
                    content_hash=content_hash(content),
                    source_channels=("fixture",),
                    bm25_score=1.0,
                    vector_score=None,
                    graph_score=None,
                    retrieval_score=1.0,
                    metadata={},
                ),
            ),
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


class FakeRetrievalService:
    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        evidence = FakeRetrievalAdapter().retrieve(request)
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=evidence,
            error=None,
            telemetry=None,
            artifacts=(),
        )


@dataclass(frozen=True)
class FakeComponents:
    service_registry: ServiceRegistry
    index_artifact_paths: dict[str, str]


class FakeProvider:
    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        return ProviderEditProposalResponse(
            text=(
                '{"target_file":"calculator.py",'
                '"new_content":"def add(a, b):\\n    return a + b\\n",'
                '"rationale":"Use addition.",'
                '"evidence_ids":["cand-1"],'
                '"risk_flags":[]}'
            ),
            tokens_in=1,
            tokens_out=1,
            model="fake",
            metadata={"provider": "fake"},
        )


class RecordingProvider(FakeProvider):
    def __init__(self) -> None:
        self.called = False

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.called = True
        return super().propose_edit(request)


def fake_component_builder(config_path: Path, *, smoke_safe: bool) -> FakeComponents:
    from homllm_v4.services.retrieval_service import EvidenceRetrievalService

    registry = ServiceRegistry()
    registry.register("evidence.retrieve", EvidenceRetrievalService(adapter=FakeRetrievalAdapter()))
    return FakeComponents(service_registry=registry, index_artifact_paths={})


def test_v3_provider_patch_factory_builds_provider_proposed_planner(tmp_path: Path) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")

    planner = build_v3_provider_proposed_patch_planner(
        config_path=Path("config.yaml"),
        workspace_root=tmp_path,
        edit_provider=FakeProvider(),
        component_builder=fake_component_builder,
    )

    assert isinstance(planner, ProviderProposedPatchPlanner)
    result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            query="fix add",
            task_class="python_patch",
            index_id="idx",
            target_file="calculator.py",
            intent="fix add",
            expected_behavior="add returns a sum",
            verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 5},
            expected_content_hash=content_hash(original),
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_plan.evidence_ids == ("cand-1",)
    assert "return a + b" in result.output.patch_request.patches[0].new_content


def test_v3_provider_patch_factory_applies_provider_prompt_limit(tmp_path: Path) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    provider = RecordingProvider()

    planner = build_v3_provider_proposed_patch_planner(
        config_path=Path("config.yaml"),
        workspace_root=tmp_path,
        edit_provider=provider,
        component_builder=fake_component_builder,
        max_prompt_chars=10,
    )

    result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            query="fix add",
            task_class="python_patch",
            index_id="idx",
            target_file="calculator.py",
            intent="fix add",
            expected_behavior="add returns a sum",
            verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 5},
            expected_content_hash=content_hash(original),
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_prompt_budget_exceeded"
    assert provider.called is False
