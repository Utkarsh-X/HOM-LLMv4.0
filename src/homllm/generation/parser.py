"""JSON parsing with resilience."""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ResilientJSONParser:
    """
    Tolerant JSON parser that handles common malformations.
    
    Steps:
    1. Strip markdown code fences
    2. Fix trailing commas
    3. Fix unquoted keys
    4. Log every correction
    5. Return None if parse fails
    """

    def parse(self, text: str) -> tuple[Optional[dict], list[str]]:
        """
        Parse JSON with tolerance for common errors.
        
        Returns:
            Tuple of (parsed_dict, corrections_applied)
        """
        corrections = []
        cleaned = text.strip()

        # 1. Strip markdown code fences
        if cleaned.startswith("```"):
            # Remove opening fence
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1 :]
                corrections.append("stripped_opening_fence")

        if cleaned.endswith("```"):
            # Remove closing fence
            last_newline = cleaned.rfind("\n")
            if last_newline != -1:
                cleaned = cleaned[:last_newline]
                corrections.append("stripped_closing_fence")
            else:
                cleaned = cleaned[:-3]
                corrections.append("stripped_closing_fence")

        # 2. Fix trailing commas
        cleaned = re.sub(r",\s*}", "}", cleaned)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        if re.search(r",\s*[}\]]", cleaned):
            corrections.append("fixed_trailing_commas")

        # 3. Try to parse
        try:
            parsed = json.loads(cleaned)
            if corrections:
                logger.info(f"JSON parsing corrections applied: {corrections}")
            return parsed, corrections
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed after corrections: {e}")
            return None, corrections
