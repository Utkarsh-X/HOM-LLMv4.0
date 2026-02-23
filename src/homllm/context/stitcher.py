"""Context stitcher implementation.

Tier 2: Deterministic semantic stitching.
Transforms ranked fragments into reasoning-aligned block grouping:
  - Intra-file: sort by line position within same-file groups
  - Inter-file: caller files before callee files (when adjacent)
  - Import injection: relevant imports prepended per file group
  - Canonical header format: --- File: X (lines N-M) [Symbol: Y] ---
"""

import logging
import re
from itertools import groupby

from homllm.context.interfaces import AllocatedBlock, Stitcher

logger = logging.getLogger(__name__)


class ContextStitcher(Stitcher):
    """Stitches blocks into final context text."""

    def __init__(self, callgraph: dict | None = None):
        self.callgraph = callgraph or {}
        # Populated after each stitch for telemetry
        self._last_stitch_telemetry: dict | None = None

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
            self._last_stitch_telemetry = None
            return ""

        # 1. Query brief
        context_parts = [f"# Query: {query}\n"]

        # 2-5. Order blocks
        if preserve_order:
            sorted_blocks = self._group_and_order(blocks)
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

        # Inject import context for each file's first block
        import_count = 0
        file_groups = self._compute_file_groups(sorted_blocks)
        import_lines = self._build_import_lines(sorted_blocks)

        # Stitch blocks with canonical headers
        seen_files: set[str] = set()
        for allocated in sorted_blocks:
            block = allocated.block
            content = allocated.truncated_content

            # Import injection: before the first block of each file
            file_key = block.file or ""
            if file_key and file_key not in seen_files and file_key in import_lines:
                imports = import_lines[file_key]
                if imports:
                    context_parts.append(f"# Imports for {file_key}:\n")
                    for imp_line in imports[:5]:  # Bounded: max 5 per file
                        context_parts.append(f"# {imp_line}\n")
                    import_count += len(imports[:5])
                seen_files.add(file_key)

            # Canonical block header
            symbol_info = f" Symbol: {block.symbol_name}" if block.symbol_name else ""
            header = f"--- File: {block.file} (lines {block.start_line}-{block.end_line}){symbol_info} ---\n"

            context_parts.append(header)
            context_parts.append(content)
            context_parts.append("\n")

        # Build telemetry
        self._last_stitch_telemetry = {
            "grouping_strategy": "same_file_adjacent" if preserve_order else ordering,
            "import_injection_count": import_count,
            "file_groups": file_groups,
            "final_block_order": [ab.block.block_id for ab in sorted_blocks],
        }

        return "\n".join(context_parts)

    def _group_and_order(self, blocks: list[AllocatedBlock]) -> list[AllocatedBlock]:
        """Group same-file blocks and sort by line position within groups.

        Algorithm:
        1. Walk blocks in ranking order.
        2. When consecutive blocks share a file, group them.
        3. Within each group, sort by start_line (reading order).
        4. For inter-file boundaries, check callgraph for caller→callee ordering.
        """
        if len(blocks) <= 1:
            return list(blocks)

        # Phase 1: Detect same-file groups while preserving ranking order
        groups: list[list[AllocatedBlock]] = []
        current_group: list[AllocatedBlock] = [blocks[0]]

        for i in range(1, len(blocks)):
            if blocks[i].block.file == current_group[-1].block.file:
                current_group.append(blocks[i])
            else:
                groups.append(current_group)
                current_group = [blocks[i]]
        groups.append(current_group)

        # Phase 2: Sort within each same-file group by start_line
        for group in groups:
            if len(group) > 1:
                group.sort(key=lambda ab: ab.block.start_line)

        # Phase 3: Inter-file caller→callee ordering for adjacent groups
        if self.callgraph and len(groups) > 1:
            groups = self._apply_callgraph_ordering(groups)

        # Flatten
        result: list[AllocatedBlock] = []
        for group in groups:
            result.extend(group)

        return result

    def _apply_callgraph_ordering(
        self, groups: list[list[AllocatedBlock]]
    ) -> list[list[AllocatedBlock]]:
        """Reorder adjacent file groups so caller appears before callee.

        Only swaps adjacent groups — no long-range moves to preserve stability.
        """
        result = list(groups)
        i = 0
        while i < len(result) - 1:
            group_a = result[i]
            group_b = result[i + 1]

            # Collect symbol_ids for each group
            ids_a = {ab.block.symbol_id for ab in group_a if ab.block.symbol_id}
            ids_b = {ab.block.symbol_id for ab in group_b if ab.block.symbol_id}

            # Check if B calls A (B is caller, A is callee) → swap so B comes first
            b_calls_a = any(
                callee in ids_a
                for sid in ids_b
                for callee in self.callgraph.get(sid, [])
            )
            a_calls_b = any(
                callee in ids_b
                for sid in ids_a
                for callee in self.callgraph.get(sid, [])
            )

            # Only swap if B→A but NOT A→B (avoid circular swaps)
            if b_calls_a and not a_calls_b:
                result[i], result[i + 1] = result[i + 1], result[i]
                i += 2  # Skip swapped pair
            else:
                i += 1

        return result

    def _build_import_lines(self, blocks: list[AllocatedBlock]) -> dict[str, list[str]]:
        """Extract import references between context files.

        For each file, find imports that reference other files in the context.
        Returns {file: [import_line, ...]}.
        """
        # Collect all files and symbols in context
        context_files = {ab.block.file for ab in blocks if ab.block.file}
        context_symbols = {
            ab.block.symbol_name
            for ab in blocks
            if ab.block.symbol_name
        }

        result: dict[str, list[str]] = {}

        for ab in blocks:
            if not ab.block.file or ab.block.file in result:
                continue

            content = ab.truncated_content or ""
            imports: list[str] = []

            # Extract import lines from content
            for line in content.split("\n"):
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue

                # Check if import references a file or symbol in context
                for other_file in context_files:
                    if other_file == ab.block.file:
                        continue
                    # Match module name from file path (e.g., "api/routes.py" → "routes")
                    module_name = other_file.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                    module_name = module_name.replace(".py", "")
                    if module_name and module_name in stripped:
                        imports.append(stripped)
                        break
                else:
                    # Check if import references a symbol in context
                    for symbol in context_symbols:
                        if symbol and symbol in stripped:
                            imports.append(stripped)
                            break

            if imports:
                result[ab.block.file] = imports[:5]  # Bounded

        return result

    def _compute_file_groups(self, blocks: list[AllocatedBlock]) -> list[dict]:
        """Compute file group summary for telemetry."""
        groups: list[dict] = []
        for file_key, group_iter in groupby(blocks, key=lambda ab: ab.block.file or ""):
            group = list(group_iter)
            lines = [ab.block.start_line for ab in group] + [ab.block.end_line for ab in group]
            groups.append({
                "file": file_key,
                "block_count": len(group),
                "line_range": f"{min(lines)}-{max(lines)}" if lines else "",
            })
        return groups
