"""Generation adapter - main orchestrator."""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Optional

from homllm.common.types import Intent
from homllm.context.interfaces import ContextArtifact
from homllm.generation.hallucination import HallucinationDetector
from homllm.generation.interfaces import (
    Diagnostics,
    GenerationRequest,
    GenerationResult,
    ModelConfig,
    ProviderConnector,
)
from homllm.generation.parser import ResilientJSONParser
from homllm.generation.providers import (
    GeminiProvider,
    GenericHTTPProvider,
    LocalProvider,
    OpenAIProvider,
)
from homllm.generation.template_loader import TemplateLoader

logger = logging.getLogger(__name__)


class GenerationAdapter:
    """
    Main generation adapter.
    
    Invariants:
    - GEN-001: Same context + same model + same config → same output (modulo model non-determinism)
    - GEN-002: Does not modify context artifact
    - GEN-003: Provider is pluggable
    - GEN-004: No retrieval or ranking logic
    - GEN-005: Raw response always persisted before parsing
    """

    def __init__(
        self,
        provider: ProviderConnector,
        template_loader: Optional[TemplateLoader] = None,
        default_template: str = "explain",
        default_model: Optional[str] = None,
    ):
        """
        Initialize generation adapter.
        
        Args:
            provider: Provider connector (LocalProvider, OpenAIProvider, etc.)
            template_loader: Template loader (default: from templates/ directory)
            default_template: Default template name
            default_model: Default model name (overrides provider default)
        """
        self.provider = provider
        self.template_loader = template_loader or TemplateLoader()
        self.default_template = default_template
        self.default_model = default_model
        self.parser = ResilientJSONParser()
        self.hallucination_detector = HallucinationDetector()

    def generate(
        self,
        request: GenerationRequest,
        stream: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> GenerationResult:
        """
        Generate response from context.
        
        Args:
            request: Generation request
            stream: Whether to stream response
            on_chunk: Callback for streaming chunks
        
        Returns:
            GenerationResult with raw_text, parsed_output, diagnostics
        
        Guarantees:
        - Raw response always persisted before parsing (GEN-005)
        - Context artifact never modified (GEN-002)
        - Deterministic for same inputs (GEN-001, modulo model non-determinism)
        """
        start_time = time.time()
        request_id = request.request_id

        try:
            # 1. Load and render template
            template_name = request.prompt_template or self.default_template
            prompt = self._render_prompt(
                template_name,
                request.query,
                request.context_artifact,
                request.template_variables,
            )

            # 2. Prepare provider request
            provider_request = self._create_provider_request(
                prompt, request.model_config, request.output_mode
            )

            # 3. Invoke provider
            if stream and on_chunk:
                provider_response = self.provider.invoke_stream(
                    provider_request, on_chunk
                )
            else:
                provider_response = self.provider.invoke_sync(provider_request)

            latency_ms = int((time.time() - start_time) * 1000)

            # 4. Store raw text BEFORE any parsing (GEN-005)
            raw_text = provider_response.text

            # 5. Parse output (if structured mode)
            parsed_output = None
            parse_warnings = []
            corrections_applied = []

            if request.output_mode in ["STRUCTURED", "TRACE"]:
                parsed, corrections = self.parser.parse(raw_text)
                parsed_output = parsed
                corrections_applied = corrections
                if parsed is None:
                    parse_warnings.append("JSON parsing failed after corrections")

            # 6. Detect hallucinations
            hallucination_flags = self.hallucination_detector.detect(
                raw_text, request.context_artifact
            )

            # 7. Build diagnostics
            diagnostics = Diagnostics(
                parse_warnings=parse_warnings,
                hallucination_flags=hallucination_flags,
                corrections_applied=corrections_applied,
            )

            # 8. Determine status based on finish reason and diagnostics
            # Priority: ERROR > truncation > parse errors > hallucinations > OK
            status: Literal["OK", "PARTIAL", "ERROR"] = "OK"
            finish_reason = provider_response.finish_reason
            
            if not raw_text:
                status = "ERROR"
            elif finish_reason in ["max_tokens", "safety", "recitation", "other"]:
                # Model was truncated - this is the PRIMARY cause of incomplete responses
                status = "PARTIAL"
                logger.warning(f"Generation truncated: finish_reason={finish_reason}")
            elif parse_warnings and request.output_mode in ["STRUCTURED", "TRACE"]:
                status = "PARTIAL"
            # Note: Hallucination flags are a quality indicator, not a generation failure
            # Commenting out to only mark PARTIAL for actual generation issues
            # elif hallucination_flags:
            #     status = "PARTIAL"

            return GenerationResult(
                request_id=request_id,
                status=status,
                provider=self.provider.__class__.__name__,
                model=provider_response.model,
                tokens_in=provider_response.tokens_in,
                tokens_out=provider_response.tokens_out,
                latency_ms=latency_ms,
                raw_text=raw_text,  # Always persisted before parsing
                parsed_output=parsed_output,
                diagnostics=diagnostics,
                finish_reason=finish_reason,
            )

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            latency_ms = int((time.time() - start_time) * 1000)

            return GenerationResult(
                request_id=request_id,
                status="ERROR",
                provider=self.provider.__class__.__name__,
                model="unknown",
                tokens_in=0,
                tokens_out=0,
                latency_ms=latency_ms,
                raw_text="",
                parsed_output=None,
                diagnostics=Diagnostics(
                    parse_warnings=[str(e)],
                    hallucination_flags=[],
                    corrections_applied=[],
                ),
                finish_reason="error",
            )

    def _render_prompt(
        self,
        template_name: str,
        query: str,
        context_artifact: ContextArtifact,
        template_variables: dict,
    ) -> str:
        """Render prompt from template."""
        variables = {
            "query": query,
            "context": context_artifact.context_text,
            **template_variables,
        }
        return self.template_loader.render(template_name, variables)

    def _create_provider_request(
        self,
        prompt: str,
        model_config: ModelConfig,
        output_mode: str,
    ) -> object:
        """Create provider request from prompt and config."""
        from homllm.generation.interfaces import ProviderRequest

        # Determine model (from adapter default or fallback)
        model = self.default_model
        if model is None:
            # Use fallback default (should come from config in production)
            model = "gemini-3.5-flash-lite"

        return ProviderRequest(
            prompt=prompt,
            model=model,
            config=model_config,
            stream=False,  # Set by caller
        )
