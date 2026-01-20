"""Generation configuration."""

from dataclasses import dataclass

from homllm.generation.interfaces import ModelConfig


@dataclass
class GenerationConfig:
    """Generation layer configuration."""

    default_provider: str
    default_model: str
    default_temperature: float
    default_max_output_tokens: int
    default_template: str = "explain"

    def get_model_config(self, **overrides) -> ModelConfig:
        """Create ModelConfig from generation config."""
        return ModelConfig(
            temperature=overrides.get("temperature", self.default_temperature),
            max_output_tokens=overrides.get(
                "max_output_tokens", self.default_max_output_tokens
            ),
            top_p=overrides.get("top_p"),
            top_k=overrides.get("top_k"),
            seed=overrides.get("seed"),
        )
