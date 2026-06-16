from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.adapters.v3_read_only_factory import build_v3_read_only_components
from homllm_v4.planning.provider_edit_proposer import (
    EditProposalProvider,
    ProviderBackedEditProposer,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanner
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


def build_v3_provider_proposed_patch_planner(
    *,
    config_path: Path,
    workspace_root: Path,
    edit_provider: EditProposalProvider,
    smoke_safe: bool = True,
    artifact_manager: ArtifactManager | None = None,
    max_prompt_chars: int | None = None,
    component_builder=build_v3_read_only_components,
) -> ProviderProposedPatchPlanner:
    components = component_builder(Path(config_path), smoke_safe=smoke_safe)
    return ProviderProposedPatchPlanner(
        retrieval_service=components.service_registry.get(
            "evidence.retrieve",
            EvidenceRetrievalService,
        ),
        direct_read_service=DirectReadService(workspace_root=Path(workspace_root)),
        edit_proposer=ProviderBackedEditProposer(
            provider=edit_provider,
            artifact_manager=artifact_manager,
            max_prompt_chars=max_prompt_chars,
        ),
    )
