"""Hallucination detection and mitigation."""

import logging
import re
from typing import Optional

from homllm.context.interfaces import ContextArtifact

logger = logging.getLogger(__name__)


class HallucinationDetector:
    """
    Detects hallucinations by cross-checking claims against context.
    
    Strategies:
    - Evidence request: Check for citations
    - Cross-check: Compare identifiers against context
    - Flag generation: Mark unverified claims
    """

    def detect(
        self, text: str, context_artifact: ContextArtifact
    ) -> list[str]:
        """
        Detect potential hallucinations in generated text.
        
        Returns:
            List of hallucination flags
        """
        flags = []

        # Extract all file:line citations
        citations = self._extract_citations(text)

        # Check each citation against context
        context_files = {block.file for block in context_artifact.blocks}
        context_lines = {
            (block.file, line)
            for block in context_artifact.blocks
            for line in range(block.start_line, block.end_line + 1)
        }

        for citation in citations:
            file_match = re.match(r"([^:]+):(\d+)", citation)
            if file_match:
                file, line_str = file_match.groups()
                try:
                    line = int(line_str)
                    if (file, line) not in context_lines:
                        flags.append(f"citation_not_in_context: {citation}")
                except ValueError:
                    flags.append(f"invalid_citation_format: {citation}")

        # Check for "NOT_IN_CONTEXT" markers (good - model is being honest)
        not_in_context_count = text.count("NOT_IN_CONTEXT")
        if not_in_context_count > 0:
            logger.info(f"Model explicitly marked {not_in_context_count} claims as NOT_IN_CONTEXT")

        # Extract function/class names mentioned
        identifiers = self._extract_identifiers(text)
        context_identifiers = {
            block.symbol_name
            for block in context_artifact.blocks
            if block.symbol_name
        }

        # Check if mentioned identifiers exist in context
        for identifier in identifiers:
            if identifier not in context_identifiers:
                # Check if it's a common word (false positive)
                if not self._is_common_word(identifier):
                    flags.append(f"identifier_not_in_context: {identifier}")

        return flags

    def _extract_citations(self, text: str) -> list[str]:
        """Extract file:line citations from text."""
        # Pattern: file.py:123 or file.py:123-456
        pattern = r"([a-zA-Z0-9_/\\-]+\.(?:py|js|ts|java|go|rs|cpp|h)):(\d+)"
        matches = re.findall(pattern, text)
        # Return full matches (file:line format)
        return [f"{file}:{line}" for file, line in matches]

    def _extract_identifiers(self, text: str) -> set[str]:
        """Extract function/class names mentioned in text."""
        # Pattern: function_name() or ClassName
        functions = re.findall(r"([a-z_][a-z0-9_]*)\s*\(", text)
        classes = re.findall(r"([A-Z][a-zA-Z0-9_]*)\b", text)
        return set(functions + classes)

    def _is_common_word(self, word: str) -> bool:
        """Check if word is a common English word (likely false positive)."""
        common_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
            "been", "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "should", "could", "may", "might", "must", "can",
        }
        return word.lower() in common_words
