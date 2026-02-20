"""Context stitcher implementation."""

from homllm.context.interfaces import AllocatedBlock, Stitcher


class ContextStitcher(Stitcher):
    """Stitches blocks into final context text."""

    def stitch(
        self,
        blocks: list[AllocatedBlock],
        query: str,
        ordering: str = "structural_first",
        preserve_order: bool = False,
    ) -> str:
        """
        Stitch blocks into final context text.
        
        Order:
        1. Query brief (one-line restatement)
        2. Structural blocks (decorators, entrypoints) in call-order
        3. Core implementation (functions, classes) by priority
        4. Helper functions
        5. Peripheral (tests, configs, summaries)
        6. Provenance appendix
        """
        if not blocks:
            return ""

        # 1. Query brief
        context_parts = [f"# Query: {query}\n"]

        # 2-5. Order blocks
        if preserve_order:
            sorted_blocks = list(blocks)
        elif ordering == "structural_first":
            # Sort by structural priority, then by file/line
            sorted_blocks = sorted(
                blocks,
                key=lambda b: (
                    "expansion:decorator" in b.block.provenance,
                    b.block.file,
                    b.block.start_line,
                ),
                reverse=True,
            )
        else:
            # Score-first: keep original order (already sorted by score)
            sorted_blocks = blocks

        # Stitch blocks with headers
        for allocated in sorted_blocks:
            block = allocated.block
            content = allocated.truncated_content

            # Create block header
            symbol_info = f" Symbol: {block.symbol_name}" if block.symbol_name else ""
            header = f"--- File: {block.file} (lines {block.start_line}-{block.end_line}){symbol_info} ---\n"

            context_parts.append(header)
            context_parts.append(content)
            context_parts.append("\n")

        # 6. Provenance appendix (optional, can be omitted for brevity)
        # For now, we'll skip it to save tokens

        return "\n".join(context_parts)
