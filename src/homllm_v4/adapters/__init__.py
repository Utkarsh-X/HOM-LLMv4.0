__all__ = (
    "V3ProviderEditProposalAdapter",
    "build_v3_provider_edit_adapter",
    "build_v3_provider_edit_adapter_from_params",
    "build_v3_provider_proposed_patch_planner",
)


def __getattr__(name: str):
    if name == "V3ProviderEditProposalAdapter":
        from homllm_v4.adapters.v3_provider_edit_proposer import V3ProviderEditProposalAdapter

        return V3ProviderEditProposalAdapter
    if name in {"build_v3_provider_edit_adapter", "build_v3_provider_edit_adapter_from_params"}:
        from homllm_v4.adapters.v3_provider_factory import (
            build_v3_provider_edit_adapter,
            build_v3_provider_edit_adapter_from_params,
        )

        return {
            "build_v3_provider_edit_adapter": build_v3_provider_edit_adapter,
            "build_v3_provider_edit_adapter_from_params": build_v3_provider_edit_adapter_from_params,
        }[name]
    if name == "build_v3_provider_proposed_patch_planner":
        from homllm_v4.adapters.v3_provider_patch_factory import build_v3_provider_proposed_patch_planner

        return build_v3_provider_proposed_patch_planner
    raise AttributeError(name)
