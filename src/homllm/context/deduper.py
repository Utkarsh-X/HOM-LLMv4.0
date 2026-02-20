"""Context block deduplication."""

from homllm.context.interfaces import ContextBlock


class ContextDeduplicator:
    """Deduplicates context blocks by structural/content similarity."""

    def deduplicate(
        self, blocks: list[ContextBlock], similarity_threshold: float = 0.9
    ) -> list[ContextBlock]:
        """
        Remove duplicate blocks based on content similarity.
        
        Args:
            blocks: List of blocks to deduplicate
            similarity_threshold: Threshold for considering blocks duplicates
        
        Returns:
            Deduplicated list preserving first-seen order
        """
        if not blocks:
            return []

        seen_content: dict[str, ContextBlock] = {}
        deduplicated: list[ContextBlock] = []

        for block in blocks:
            # Use content hash for exact-prefix deduplication
            content_key = block.content[:200] if block.content else block.block_id
            if content_key in seen_content:
                continue

            # Span overlap deduplication within same file
            overlapped_index = None
            for idx, existing in enumerate(deduplicated):
                if not block.file or not existing.file or block.file != existing.file:
                    continue
                if self._span_overlap_ratio(block, existing) >= similarity_threshold:
                    overlapped_index = idx
                    break

            if overlapped_index is None:
                seen_content[content_key] = block
                deduplicated.append(block)
                continue

            # Keep both if spans/symbols clearly differ enough to preserve coverage.
            existing = deduplicated[overlapped_index]
            # If both blocks refer to distinct symbols, keep both to preserve granularity.
            if block.symbol_id and existing.symbol_id and block.symbol_id != existing.symbol_id:
                seen_content[content_key] = block
                deduplicated.append(block)
                continue
            # If one span is much larger, keep both to avoid collapsing detail.
            smaller = min(self._span_length(block), self._span_length(existing))
            larger = max(self._span_length(block), self._span_length(existing))
            if smaller > 0 and larger / smaller >= 5:
                seen_content[content_key] = block
                deduplicated.append(block)
            # Else: duplicate overlap, drop later block to preserve ranking order.

        return deduplicated

    def _span_length(self, block: ContextBlock) -> int:
        if block.start_line and block.end_line and block.end_line >= block.start_line:
            return block.end_line - block.start_line + 1
        return len(block.content.splitlines()) if block.content else 0

    def _span_overlap_ratio(self, a: ContextBlock, b: ContextBlock) -> float:
        if a.start_line is None or a.end_line is None:
            return 0.0
        if b.start_line is None or b.end_line is None:
            return 0.0
        if a.file != b.file:
            return 0.0
        start = max(a.start_line, b.start_line)
        end = min(a.end_line, b.end_line)
        if start > end:
            return 0.0
        overlap = end - start + 1
        # Use the smaller span to detect containment redundancy.
        length = min(self._span_length(a), self._span_length(b))
        return overlap / length if length > 0 else 0.0
