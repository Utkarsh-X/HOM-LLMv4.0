#!/usr/bin/env python3
"""
Canonical entrypoint for running a query end-to-end.

Usage:
    python runtime/run_query.py --query "..." [--config <path>] [--json] [--provider <name>] [--model <name>]
"""
from pathlib import Path
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import bootstrap
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
import logging

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from homllm.common.config import Config
from homllm.common.types import Intent
from homllm.context.pipeline import ContextPipeline
from homllm.generation.adapter import GenerationAdapter
from homllm.generation.interfaces import GenerationRequest, ModelConfig
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.storage.filesystem_adapter import FilesystemAdapter
from homllm.ranking.pipeline import RankingPipeline
from homllm.retrieval.pipeline import RetrievalPipeline
from runtime.logger import configure_logging


def format_duration_ms(start: float, end: float) -> float:
    """Convert duration to milliseconds."""
    return (end - start) * 1000


logger = configure_logging(logger_name=__name__)


class PresentationRenderer:
    """
    Architecture-safe presentation renderer for user-facing output.
    
    Responsibilities:
    - Remove/abstract internal grounding markers (file hashes, symbol IDs)
    - Map file IDs to real file paths if shown
    - Map PARTIAL status to neutral user message
    - Preserve raw artifacts unchanged
    
    Constraints:
    - Pure, stateless, O(n) string processing
    - Configurable and bypassable for debug mode
    - No side effects on core logic
    """
    
    def __init__(
        self,
        artifacts_path: Path,
        normalize: bool = True,
        map_file_ids: bool = True,
    ):
        """
        Initialize presentation renderer.
        
        Args:
            artifacts_path: Path to indexes directory (for files.json)
            normalize: Enable normalization (disable for debug mode)
            map_file_ids: Map file hashes to real paths
        """
        self.artifacts_path = artifacts_path
        self.normalize = normalize
        self.map_file_ids = map_file_ids
        self._file_id_map: dict[str, str] | None = None
    
    def _load_file_metadata(self) -> dict[str, str]:
        """Lazy-load file_id -> path mapping."""
        if self._file_id_map is not None:
            return self._file_id_map
        
        self._file_id_map = {}
        try:
            fs_adapter = FilesystemAdapter(self.artifacts_path)
            if fs_adapter.exists("files.json"):
                files_data = fs_adapter.read_json("files.json")
                for file_info in files_data.get("files", []):
                    file_id = file_info.get("file_id")
                    file_path = file_info.get("path")
                    if file_id and file_path:
                        self._file_id_map[file_id] = file_path
        except Exception:
            # If metadata unavailable, continue without mapping
            pass
        
        return self._file_id_map
    
    def render(
        self,
        raw_text: str,
        status: str = "OK",
    ) -> str:
        """
        Render user-facing output from raw generation text.
        
        Args:
            raw_text: Raw generation output (preserved in artifacts)
            status: Generation status (OK, PARTIAL, ERROR)
        
        Returns:
            Normalized user-facing text
        """
        if not self.normalize:
            return raw_text
        
        import re
        text = raw_text
        
        # Load file metadata if mapping enabled
        file_id_map = {}
        if self.map_file_ids:
            file_id_map = self._load_file_metadata()
        
        # Pattern 1: Remove file:line citations (e.g., "file.py:123" or "file.py:123-456")
        text = re.sub(
            r'\b[a-zA-Z0-9_/\\-]+\.(?:py|js|ts|java|go|rs|cpp|h):\d+(?:-\d+)?\b',
            '',
            text
        )
        
        # Pattern 2: Remove symbol IDs (e.g., "48dc8273aeda9734:_compute_file_hash:77")
        # Format: file_id:symbol_name:line (file_id is 16 hex chars)
        def replace_symbol_id(match: re.Match) -> str:
            full_match = match.group(0)
            parts = full_match.split(':')
            if len(parts) >= 3:
                file_id = parts[0]
                symbol_name = parts[1]
                line = parts[2]
                # If mapping enabled and file_id found, optionally show file path
                # Otherwise remove entirely (internal grounding marker)
                if self.map_file_ids and file_id_map and file_id in file_id_map:
                    file_path = file_id_map[file_id]
                    # Return readable format: file_path:symbol_name:line
                    return f"{file_path}:{symbol_name}:{line}"
                return ""  # Remove internal grounding markers
            return ""
        
        # Match symbol IDs: 16 hex chars : symbol_name : line number
        text = re.sub(
            r'\b[a-f0-9]{16}:[a-zA-Z0-9_]+:\d+\b',
            replace_symbol_id,
            text
        )
        
        # Pattern 3: Remove standalone file hash references (internal IDs)
        # These are internal grounding markers, not user-facing citations
        # Match 16 hex char file IDs that appear standalone (not in symbol ID format)
        text = re.sub(
            r'\b([a-f0-9]{16})\b(?!:[a-zA-Z0-9_]+:\d)',  # Negative lookahead: not followed by :symbol:line
            '',
            text
        )
        
        # Pattern 4: Remove standalone "NOT_IN_CONTEXT" markers
        text = re.sub(r'\bNOT_IN_CONTEXT\b', '', text, flags=re.IGNORECASE)
        
        # Pattern 5: Remove parenthetical citations like "(file.py:123)" or "[file.py:123]"
        text = re.sub(
            r'[\(\[][a-zA-Z0-9_/\\-]+\.(?:py|js|ts|java|go|rs|cpp|h):\d+(?:-\d+)?[\)\]]',
            '',
            text
        )
        
        # Clean up extra whitespace left by removed citations
        text = re.sub(r' {2,}', ' ', text)  # Multiple spaces -> single space
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines -> double newline
        
        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    def render_status_message(self, status: str) -> str | None:
        """
        Map internal status to neutral user-facing message.
        
        Args:
            status: Internal status (OK, PARTIAL, ERROR)
        
        Returns:
            User-facing message or None if no message needed
        """
        if not self.normalize:
            return None
        
        if status == "PARTIAL":
            return "Note: Some claims could not be fully verified from the provided context."
        
        return None


def print_telemetry(phase: str, **kwargs):
    """Print telemetry line in consistent format (duration-focused)."""
    parts = [f"[{phase}]"]
    for key, value in kwargs.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.2f}")
        else:
            parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


class QueryTelemetry:
    """Telemetry collector for query execution."""

    def __init__(self, query: str, export_json: bool = False):
        self.query = query
        self.should_export_json = export_json
        self.run_id = str(uuid.uuid4())
        self.phases = {}

    def record_phase(
        self,
        phase: str,
        start_time: float,
        end_time: float,
        **metadata,
    ):
        """Record phase telemetry."""
        duration_ms = format_duration_ms(start_time, end_time)

        phase_data = {
            "phase": phase,
            "duration_ms": duration_ms,
            **metadata,
        }

        self.phases[phase] = phase_data

        # Print telemetry
        print_telemetry(phase, duration_ms=f"{duration_ms:.0f}", **metadata)

    def write_json(self, output_path: Path):
        """Export telemetry as JSON."""
        telemetry_data = {
            "run_id": self.run_id,
            "query": self.query,
            "phases": self.phases,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(telemetry_data, f, indent=2)

        print_telemetry("TELEMETRY", json_export=str(output_path))


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(description="Run a query end-to-end")
    parser.add_argument("--query", type=str, required=True, help="Query string")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"), help="Config file path")
    parser.add_argument("--json", action="store_true", help="Export JSON telemetry")
    parser.add_argument("--provider", type=str, help="Generation provider (gemini, openai, local)")
    parser.add_argument("--model", type=str, help="Generation model name")
    parser.add_argument("--intent", type=str, default="UNKNOWN", help="Query intent")
    parser.add_argument("--raw", action="store_true", help="Disable presentation normalization (debug mode)")
    parser.add_argument("--no-file-mapping", action="store_true", help="Disable file ID to path mapping")

    args = parser.parse_args()

    # Load config
    if not args.config.exists():
        logger.error(f"Error: Config file does not exist: {args.config}")
        sys.exit(1)

    try:
        config = Config.from_file(args.config)
        indexer_config = config.get_indexer_config()
        retrieval_config = config.get_retrieval_config()
        ranking_config = config.get_ranking_config()
        context_config = config.get_context_config()
        generation_config = config.get_generation_config()
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

    # Initialize telemetry
    telemetry = QueryTelemetry(args.query, export_json=args.json)

    # Parse intent
    try:
        intent = Intent[args.intent.upper()]
    except KeyError:
        intent = Intent.UNKNOWN

    try:
        # Initialize presentation renderer (architecture-safe, deterministic)
        presentation_renderer = PresentationRenderer(
            artifacts_path=indexer_config.storage.artifacts_path,
            normalize=not args.raw,
            map_file_ids=not args.no_file_mapping,
        )

        # Initialize embedder (shared across retrieval and context)
        embedder = QwenEmbedder(
            model_name=indexer_config.embedding_model,
            dimension=indexer_config.embedding_dimension,
        )

        # Phase 1: Retrieval
        retrieval_start = time.perf_counter()
        retrieval_pipeline = RetrievalPipeline(
            config=retrieval_config,
            bm25_index_path=indexer_config.storage.tantivy_path,
            vector_db_path=indexer_config.storage.lancedb_path,
            duckdb_path=indexer_config.storage.duckdb_path,
            artifacts_path=indexer_config.storage.artifacts_path,
            embedder=embedder,
        )

        retrieval_result = retrieval_pipeline.retrieve(args.query, intent=intent)
        retrieval_end = time.perf_counter()

        telemetry.record_phase(
            "RETRIEVAL",
            retrieval_start,
            retrieval_end,
            candidates=len(retrieval_result.candidates),
            bm25_count=retrieval_result.metadata.get("bm25_count", 0),
            vector_count=retrieval_result.metadata.get("vector_count", 0),
            merged_count=retrieval_result.metadata.get("merged_count", 0),
        )

        if not retrieval_result.candidates:
            logger.warning("No candidates retrieved")
            return

        # Phase 2: Ranking
        ranking_start = time.perf_counter()

        # Load callgraph for ranking
        callgraph = {}
        fs_adapter = FilesystemAdapter(indexer_config.storage.artifacts_path)
        if fs_adapter.exists("callgraph.json"):
            callgraph_data = fs_adapter.read_json("callgraph.json")
            for edge in callgraph_data.get("edges", []):
                caller_id = edge.get("caller_id")
                callee_id = edge.get("callee_id")
                if caller_id and callee_id:
                    if caller_id not in callgraph:
                        callgraph[caller_id] = []
                    callgraph[caller_id].append(callee_id)

        ranking_pipeline = RankingPipeline(
            config=ranking_config,
            callgraph=callgraph,
        )

        from homllm.ranking.interfaces import RankingInput

        ranking_input = RankingInput(
            query=args.query,
            candidates=tuple(retrieval_result.candidates),
            config=ranking_config,
        )

        ranking_output = ranking_pipeline.rank(ranking_input)
        ranking_end = time.perf_counter()

        telemetry.record_phase(
            "RANKING",
            ranking_start,
            ranking_end,
            candidates=len(ranking_output.ranked_candidates),
            reranker=ranking_output.metadata.reranker_used,
            reranker_unavailable=ranking_output.metadata.reranker_unavailable,
        )

        # Phase 3: Context Assembly
        context_start = time.perf_counter()
        context_pipeline = ContextPipeline(
            config=context_config,
            embedder=embedder,
        )

        context_artifact = context_pipeline.assemble(
            ranking_output=ranking_output,
            query=args.query,
            query_id=retrieval_result.query_id,
        )
        context_end = time.perf_counter()

        telemetry.record_phase(
            "CONTEXT",
            context_start,
            context_end,
            blocks=len(context_artifact.blocks),
            tokens=context_artifact.used_tokens,
            token_budget=context_artifact.token_budget,
            generation_reserve=context_config.generation_reserve_tokens,
            tokens_remaining=context_config.max_tokens - context_artifact.used_tokens,
        )

        # Phase 4: Generation
        generation_start = time.perf_counter()

        # Select provider
        provider_name = args.provider or generation_config.default_provider
        if provider_name == "gemini":
            from homllm.generation.providers import GeminiProvider

            provider = GeminiProvider()
        elif provider_name == "openai":
            from homllm.generation.providers import OpenAIProvider

            provider = OpenAIProvider()
        elif provider_name == "local":
            from homllm.generation.providers import LocalProvider

            provider = LocalProvider()
        else:
            logger.error(f"Error: Unknown provider: {provider_name}")
            sys.exit(1)

        model_name = args.model or generation_config.default_model
        generation_adapter = GenerationAdapter(
            provider=provider,
            default_model=model_name,
        )

        model_config = ModelConfig(
            temperature=generation_config.default_temperature,
            max_output_tokens=generation_config.default_max_output_tokens,
        )

        generation_request = GenerationRequest(
            request_id=retrieval_result.query_id,
            query=args.query,
            intent=intent,
            context_artifact=context_artifact,
            prompt_template="explain",
            template_variables={},
            output_mode="TEXT",
            model_config=model_config,
        )

        generation_result = generation_adapter.generate(generation_request)
        generation_end = time.perf_counter()

        telemetry.record_phase(
            "GENERATION",
            generation_start,
            generation_end,
            provider=provider_name,
            model=generation_result.model,
            tokens_in=generation_result.tokens_in,
            tokens_out=generation_result.tokens_out,
            status=generation_result.status,
            finish_reason=generation_result.finish_reason,
        )

        # Render user-facing output (preserves raw_text in artifacts)
        rendered_output = presentation_renderer.render(
            raw_text=generation_result.raw_text,
            status=generation_result.status,
        )
        
        # Print result (structured logging)
        logger.info("=" * 80)
        logger.info("RESULT:")
        for line in rendered_output.splitlines():
            logger.info(line)
        logger.info("=" * 80)
        
        # Show status message if PARTIAL
        status_message = presentation_renderer.render_status_message(generation_result.status)
        if status_message:
            logger.info(status_message)

        # Export JSON if requested
        if args.json:
            artifacts_path = Path("artifacts") / "runs" / telemetry.run_id
            telemetry.write_json(artifacts_path / "telemetry.json")

    except Exception as e:
        logger.error(f"Error during query execution: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
