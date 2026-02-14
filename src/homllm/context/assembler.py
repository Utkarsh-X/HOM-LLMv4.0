"""Context block assembler - converts candidates to blocks."""

import logging
from typing import Optional

from homllm.context.interfaces import ContextBlock
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


class BlockAssembler:
    """Assembles context blocks from ranked candidates."""

    def assemble(self, candidates: list[Candidate]) -> list[ContextBlock]:
        """
        Convert candidates to context blocks.
        
        Args:
            candidates: Ranked candidates from ranking layer
        
        Returns:
            List of context blocks with file/line information
        """
        blocks = []

        for candidate in candidates:
            # Extract file and symbol info from candidate
            file_path = candidate.file
            symbol_id = candidate.symbol_id
            content = candidate.content or ""

            # Parse symbol_id to extract line numbers if available
            # Format: file_id:symbol_id or symbol_id:start_line:end_line
            start_line = candidate.span_start if candidate.span_start is not None else 1
            if candidate.span_end is not None:
                end_line = candidate.span_end
            else:
                end_line = start_line + (len(content.split("\n")) - 1 if content else 0)

            if symbol_id and ":" in symbol_id:
                parts = symbol_id.split(":")
                # Try to extract line numbers if present
                try:
                    if len(parts) >= 3:
                        parsed_start = int(parts[-2])
                        parsed_end = int(parts[-1])
                        if candidate.span_start is None:
                            start_line = parsed_start
                        if candidate.span_end is None:
                            end_line = parsed_end
                except ValueError:
                    pass

            # Extract symbol name
            symbol_name = None
            if symbol_id:
                symbol_name = symbol_id.split(":")[-1] if ":" in symbol_id else symbol_id

            block = ContextBlock(
                block_id=candidate.doc_id,
                file=file_path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                symbol_id=symbol_id,
                symbol_name=symbol_name,
                provenance=candidate.provenance,
            )

            blocks.append(block)

        return blocks
