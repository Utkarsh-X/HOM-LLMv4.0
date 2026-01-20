"""Context block deduplication."""

from homllm.context.interfaces import ContextBlock


class ContextDeduplicator:
    """Deduplicates context blocks by content similarity."""

    def deduplicate(
        self, blocks: list[ContextBlock], similarity_threshold: float = 0.9
    ) -> list[ContextBlock]:
        """
        Remove duplicate blocks based on content similarity.
        
        Args:
            blocks: List of blocks to deduplicate
            similarity_threshold: Threshold for considering blocks duplicates
        
        Returns:
            Deduplicated list, keeping first occurrence
        """
        if not blocks:
            return []

        seen_content: dict[str, ContextBlock] = {}
        deduplicated = []

        for block in blocks:
            # Use content hash for deduplication
            content_key = block.content[:200] if block.content else block.block_id

            if content_key not in seen_content:
                seen_content[content_key] = block
                deduplicated.append(block)

        return deduplicated
