import json
from pathlib import Path

from homllm_v4.planning.direct_provider_patch_planner import DirectProviderPatchPlanner
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.services.direct_read_service import DirectReadService


class RecordingProvider:
    def __init__(self, new_content: str) -> None:
        self.new_content = new_content
        self.prompts: list[str] = []

    def propose_edit(self, request):
        self.prompts.append(request.prompt)
        evidence_ids = ()
        for line in request.prompt.splitlines():
            if line.startswith("Evidence IDs:"):
                evidence_ids = tuple(
                    item.strip()
                    for item in line.removeprefix("Evidence IDs:").split(",")
                    if item.strip()
                )
                break
        return ProviderEditProposalResponse(
            text=json.dumps(
                {
                    "target_file": "demo.py",
                    "new_content": self.new_content,
                    "rationale": "Direct provider baseline edit.",
                    "evidence_ids": list(evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=11,
            tokens_out=7,
            model="fake-direct",
            metadata={"provider": "test"},
        )


def _request(tmp_path: Path, target_file: str | None = "demo.py") -> ProviderProposedPatchPlanRequest:
    return ProviderProposedPatchPlanRequest(
        task_id="direct-provider-test",
        workspace_root=str(tmp_path),
        query="change demo value",
        task_class="patch",
        index_id="unused",
        target_file=target_file,
        intent="Change VALUE to 2.",
        expected_behavior="VALUE equals 2.",
        verification_argv=("python", "-m", "compileall", "-q", "demo.py"),
        retrieval_policy={},
    )


def test_direct_provider_patch_planner_builds_patch_without_retrieval_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = RecordingProvider("VALUE = 2\n")
    planner = DirectProviderPatchPlanner(
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(_request(tmp_path))

    assert result.ok
    assert result.output is not None
    patch_request = result.output.patch_request
    assert patch_request.patches[0].file_path == "demo.py"
    assert patch_request.patches[0].new_content == "VALUE = 2\n"
    assert provider.prompts
    assert "Evidence context: none supplied" in provider.prompts[0]
    assert result.telemetry.output_summary["planner_context_mode"] == "direct_provider"
    assert result.telemetry.output_summary["target_selection_decision"] == "direct_supplied"
    assert result.telemetry.output_summary["resolved_target_file"] == "demo.py"
    assert result.telemetry.output_summary["evidence_context_item_count"] == 0
    assert result.telemetry.token_usage == {"input": 11, "output": 7}


def test_direct_provider_patch_planner_requires_supplied_target_file(
    tmp_path: Path,
) -> None:
    provider = RecordingProvider("VALUE = 2\n")
    planner = DirectProviderPatchPlanner(
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(_request(tmp_path, target_file=None))

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "direct_provider_target_required"
    assert provider.prompts == []
