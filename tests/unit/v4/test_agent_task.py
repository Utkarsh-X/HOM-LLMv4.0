import json
import sys
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanner
from homllm_v4.runtime.agent_task import AgentTaskRequest, run_agent_task
from homllm_v4.services.direct_read_service import DirectReadService


class SingleFileRetrievalService:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        target_file = request.target_files[0]
        content = (self.workspace_root / target_file).read_text(encoding="utf-8")
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=EvidenceSet(
                evidence_set_id=f"{request.task_id}:evidence",
                query=request.query,
                candidates=(
                    EvidenceCandidate(
                        candidate_id=f"{request.task_id}:candidate:{target_file}",
                        file_path=target_file,
                        symbol_id=None,
                        span_start=1,
                        span_end=len(content.splitlines()),
                        content_hash="hash",
                        source_channels=("test",),
                        bm25_score=None,
                        vector_score=None,
                        graph_score=None,
                        retrieval_score=1.0,
                        metadata={"content": content},
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
            ),
            error=None,
            telemetry=None,
            artifacts=(),
        )


class ReplacingProvider:
    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        target_file = ""
        current_content_lines: list[str] = []
        in_current_content = False
        evidence_ids = ()
        for line in request.prompt.splitlines():
            if line.startswith("Target file:"):
                target_file = line.removeprefix("Target file:").strip()
            elif line.startswith("Evidence IDs:"):
                evidence_ids = tuple(
                    item.strip()
                    for item in line.removeprefix("Evidence IDs:").split(",")
                    if item.strip()
                )
            elif line == "Current content:":
                in_current_content = True
            elif in_current_content:
                current_content_lines.append(line)
        current_content = "\n".join(current_content_lines)
        if request.prompt.endswith("\n"):
            current_content = f"{current_content}\n"
        new_content = current_content.replace(
            "return text.upper()",
            "return text.strip().upper()",
        )
        return ProviderEditProposalResponse(
            text=json.dumps(
                {
                    "target_file": target_file,
                    "new_content": new_content,
                    "rationale": "Strip whitespace before uppercasing.",
                    "evidence_ids": list(evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=10,
            tokens_out=5,
            model="fake-test",
            metadata={"provider": "test"},
        )


def test_run_agent_task_applies_and_verifies_single_live_style_edit(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "sku.py").write_text(
        "def normalize(text: str) -> str:\n    return text.upper()\n",
        encoding="utf-8",
    )

    def build_provider(**kwargs):
        return ReplacingProvider()

    def build_planner(**kwargs):
        root = Path(kwargs["workspace_root"])
        return ProviderProposedPatchPlanner(
            retrieval_service=SingleFileRetrievalService(root),
            direct_read_service=DirectReadService(workspace_root=root),
            edit_proposer=ProviderBackedEditProposer(
                provider=kwargs["edit_provider"],
                artifact_manager=kwargs["artifact_manager"],
                max_prompt_chars=kwargs["max_prompt_chars"],
            ),
        )

    result = run_agent_task(
        AgentTaskRequest(
            config_path=tmp_path / "config.yaml",
            workspace_root=workspace,
            artifact_root=tmp_path / "runs",
            run_id="agent-task-test",
            query="normalize should strip whitespace before uppercasing",
            intent="Make normalize strip surrounding whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=(
                sys.executable,
                "-c",
                "from sku import normalize; "
                "raise SystemExit(0 if normalize(' sku ') == 'SKU' else 1)",
            ),
            live_api_key="test-key",
            provider_builder=build_provider,
            planner_builder=build_planner,
        )
    )

    assert result.stop_reason == "verified"
    assert result.error_code is None
    assert result.patch_attempt_count == 1
    assert result.verification_count == 1
    assert "strip().upper()" in (workspace / "sku.py").read_text(encoding="utf-8")
    assert (
        tmp_path / "runs" / "agent-task-test" / "provider" / "agent-task-test" / "prompt.txt"
    ).is_file()


def test_run_agent_task_can_prepare_run_local_index_config(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "sku.py").write_text(
        "def normalize(text: str) -> str:\n    return text.upper()\n",
        encoding="utf-8",
    )
    template_config = tmp_path / "template.yaml"
    template_config.write_text(
        """
indexer:
  storage:
    duckdb_path: old/metadata.duckdb
    tantivy_path: old/bm25.index
    lancedb_path: old/vectors.lance
    artifacts_path: old
  vector_indexing_enabled: true
retrieval: {}
ranking: {}
context: {}
generation: {}
evaluation: {}
""".strip(),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def build_index(**kwargs):
        captured["index_config_path"] = Path(kwargs["config_path"])
        captured["index_workspace_root"] = Path(kwargs["workspace_root"])
        captured["skip_vectors"] = kwargs["skip_vectors"]
        artifacts_path = Path(kwargs["artifact_paths"]["artifacts"])
        artifacts_path.mkdir(parents=True, exist_ok=True)
        (artifacts_path / "metadata.duckdb").write_text("duck", encoding="utf-8")
        (artifacts_path / "bm25.index").mkdir()
        return {"source_file_count": 1, "symbol_count": 1}

    def build_provider(**kwargs):
        return ReplacingProvider()

    def build_planner(**kwargs):
        captured["planner_config_path"] = Path(kwargs["config_path"])
        root = Path(kwargs["workspace_root"])
        return ProviderProposedPatchPlanner(
            retrieval_service=SingleFileRetrievalService(root),
            direct_read_service=DirectReadService(workspace_root=root),
            edit_proposer=ProviderBackedEditProposer(
                provider=kwargs["edit_provider"],
                artifact_manager=kwargs["artifact_manager"],
                max_prompt_chars=kwargs["max_prompt_chars"],
            ),
        )

    result = run_agent_task(
        AgentTaskRequest(
            config_path=template_config,
            workspace_root=workspace,
            artifact_root=tmp_path / "runs",
            run_id="agent-task-index-test",
            query="normalize should strip whitespace before uppercasing",
            intent="Make normalize strip surrounding whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=(
                sys.executable,
                "-c",
                "from sku import normalize; "
                "raise SystemExit(0 if normalize(' sku ') == 'SKU' else 1)",
            ),
            live_api_key="test-key",
            prepare_index=True,
            index_skip_vectors=True,
            index_builder=build_index,
            provider_builder=build_provider,
            planner_builder=build_planner,
        )
    )

    generated_config = (
        tmp_path
        / "runs"
        / "agent-task-index-test"
        / "index"
        / "generated_config.yaml"
    )
    assert result.stop_reason == "verified"
    assert result.index_built is True
    assert result.index_config_path == str(generated_config.resolve())
    assert captured["index_config_path"] == generated_config.resolve()
    assert captured["planner_config_path"] == generated_config.resolve()
    assert captured["index_workspace_root"] == workspace.resolve()
    assert captured["skip_vectors"] is True
    config_text = generated_config.read_text(encoding="utf-8")
    assert "agent-task-index-test/index/metadata.duckdb" in config_text.replace("\\", "/")
    assert "vector_indexing_enabled: false" in config_text
