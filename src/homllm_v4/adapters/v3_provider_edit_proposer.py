from __future__ import annotations

from dataclasses import dataclass

from homllm.generation.interfaces import ModelConfig, ProviderConnector, ProviderRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)


@dataclass(frozen=True)
class V3ProviderEditProposalAdapter:
    provider: ProviderConnector
    model: str
    model_config: ModelConfig

    def propose_edit(
        self,
        request: ProviderEditProposalRequest,
    ) -> ProviderEditProposalResponse:
        response = self.provider.invoke_sync(
            ProviderRequest(
                prompt=request.prompt,
                model=self.model,
                config=self.model_config,
                stream=False,
            )
        )
        return ProviderEditProposalResponse(
            text=response.text,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            model=response.model,
            metadata={**response.metadata, "finish_reason": response.finish_reason},
        )
