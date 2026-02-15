"""Hierarchical chunking for multi-granularity indexing.

This module creates 3-level hierarchical chunks:
- Fine: Symbol-level (functions, methods, classes)
- Medium: File sections / logical blocks
- Coarse: File-level summary (docstrings + signatures)

Chunking Principles:
- Deterministic (no heuristics at runtime)
- No LLM inference
- Pure structural analysis
"""

import hashlib
import logging
import textwrap
from dataclasses import dataclass
from typing import Optional

from homllm.common.config import HierarchicalChunkingConfig
from homllm.common.types import ChunkInfo, EntityInfo, GranularityLevel, SymbolInfo

logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context for chunking a single file."""
    
    file_path: str
    content: str
    lines: list[str]
    symbols: list[SymbolInfo]
    entities: list[EntityInfo]


class HierarchicalChunker:
    """
    Creates multi-granularity chunks for indexing.
    
    Supports three levels:
    - Fine: One chunk per symbol (function, method, class)
    - Medium: Logical file sections (groups of related symbols)
    - Coarse: File-level summary (docstrings + signatures only)
    
    All chunking is deterministic and structural.
    """
    
    def __init__(self, config: HierarchicalChunkingConfig):
        """
        Initialize hierarchical chunker.
        
        Args:
            config: Chunking configuration with level toggles
        """
        self.config = config
        self.chunk_max_lines = max(1, int(config.chunk_max_lines))
    
    def create_chunks(
        self,
        file_path: str,
        content: str,
        symbols: list[SymbolInfo],
        entities: list[EntityInfo],
    ) -> list[ChunkInfo]:
        """
        Create hierarchical chunks for a file.
        
        Args:
            file_path: Path to the file
            content: File content
            symbols: Extracted symbols from parser
            entities: Extracted entities from entity extractor
            
        Returns:
            List of ChunkInfo at all enabled granularity levels
        """
        if not self.config.enabled:
            return []
        
        lines = content.split("\n")
        context = FileContext(
            file_path=file_path,
            content=content,
            lines=lines,
            symbols=symbols,
            entities=entities,
        )
        
        chunks = []
        
        # Fine-level chunks (symbol-level)
        if self.config.fine_enabled:
            chunks.extend(self._create_fine_chunks(context))
        
        # Medium-level chunks (file sections)
        if self.config.medium_enabled:
            chunks.extend(self._create_medium_chunks(context))
        
        # Coarse-level chunks (file summary)
        if self.config.coarse_enabled:
            chunks.extend(self._create_coarse_chunks(context))
        
        return chunks
    
    def _compute_chunk_id(
        self,
        file_path: str,
        granularity: str,
        index: int,
    ) -> str:
        """Compute stable chunk ID."""
        key = f"{file_path}:{granularity}:{index}"
        return hashlib.sha256(key.encode()).hexdigest()[:24]
    
    def _create_fine_chunks(self, context: FileContext) -> list[ChunkInfo]:
        """
        Create fine-level (symbol-level) chunks with parent scope injection.
        
        Each fine chunk includes:
        - File header for explicit location context
        - Parent scope signatures (class / outer function chain)
        - Symbol body normalized to match injected nesting depth
        """
        chunks = []
        chunk_idx = 0
        symbol_by_id = {s.id: s for s in context.symbols}

        for symbol in context.symbols:
            # Skip very small symbols (less than 2 lines)
            if symbol.end_line - symbol.start_line < 2:
                continue

            # Build scope-aware fine chunk to avoid orphaned method/function bodies.
            scope_chain = self._build_scope_chain(symbol, symbol_by_id)
            chunk_prefix = [f"# File: {context.file_path}", ""]
            
            for depth, parent in enumerate(scope_chain):
                scope_line = self._get_scope_signature(parent)
                chunk_prefix.append(self._indent_content(scope_line, depth))
            chunk_prefix = self._fit_fine_prefix(chunk_prefix)

            max_body_lines = max(1, self.chunk_max_lines - len(chunk_prefix))
            for segment_start, segment_end in self._iter_line_windows(
                symbol.start_line,
                symbol.end_line,
                max_lines=max_body_lines,
            ):
                start_idx = max(0, segment_start - 1)
                end_idx = min(len(context.lines), segment_end)
                raw_segment = "\n".join(context.lines[start_idx:end_idx])
                normalized_content = self._normalize_symbol_content(raw_segment)

                chunk_parts = list(chunk_prefix)
                chunk_parts.append(
                    self._indent_content(normalized_content, len(scope_chain))
                )
                chunk_content = "\n".join(chunk_parts)

                linked_entities = self._find_linked_entities(
                    segment_start,
                    segment_end,
                    context.entities,
                )
                chunk = ChunkInfo(
                    chunk_id=self._compute_chunk_id(
                        context.file_path,
                        GranularityLevel.FINE.value,
                        chunk_idx,
                    ),
                    file_path=context.file_path,
                    content=chunk_content,
                    granularity_level=GranularityLevel.FINE.value,
                    span_start=segment_start,
                    span_end=segment_end,
                    entity_ids=tuple(linked_entities),
                )
                chunks.append(chunk)
                chunk_idx += 1

        return chunks
    
    def _build_scope_chain(
        self,
        symbol: SymbolInfo,
        symbol_by_id: dict[str, SymbolInfo],
    ) -> list[SymbolInfo]:
        """
        Build parent scope chain from root -> immediate parent for a symbol.
        """
        chain = []
        current = symbol
        
        while current.parent_id:
            parent = symbol_by_id.get(current.parent_id)
            if not parent:
                break
            chain.insert(0, parent)
            current = parent
        
        return chain
    
    def _get_scope_signature(self, symbol: SymbolInfo) -> str:
        """
        Return a signature-only line for an enclosing scope.
        """
        if symbol.kind.value == "class":
            return f"class {symbol.name}:"
        
        if symbol.kind.value in {"function", "method"}:
            if symbol.signature:
                return f"def {symbol.signature}:"
            return f"def {symbol.name}(...):"
        
        return f"# {symbol.name}"
    
    def _normalize_symbol_content(self, content: str) -> str:
        """
        Dedent symbol content so scope injection can re-indent deterministically.
        """
        return textwrap.dedent(content).rstrip()
    
    def _indent_content(self, content: str, levels: int) -> str:
        """
        Indent multi-line content by 4 spaces per level.
        """
        if levels <= 0:
            return content
        
        prefix = "    " * levels
        lines = content.split("\n")
        return "\n".join(f"{prefix}{line}" if line else line for line in lines)
    
    def _create_medium_chunks(self, context: FileContext) -> list[ChunkInfo]:
        """
        Create medium-level (file section) chunks.
        
        Groups symbols by:
        1. Class membership (all methods of a class)
        2. Logical sections (separated by blank lines or docstrings)
        """
        chunks = []
        
        # Group symbols by class
        class_symbols = {}
        standalone_symbols = []
        
        for symbol in context.symbols:
            if symbol.kind.value == "class":
                class_symbols[symbol.id] = [symbol]
            elif symbol.parent_id:
                if symbol.parent_id in class_symbols:
                    class_symbols[symbol.parent_id].append(symbol)
                else:
                    # Parent not found, treat as standalone
                    standalone_symbols.append(symbol)
            else:
                standalone_symbols.append(symbol)
        
        chunk_idx = 0
        
        # Create chunks for each class
        for class_id, class_group in class_symbols.items():
            if not class_group:
                continue
            
            # Find the class symbol
            class_symbol = class_group[0]
            if class_symbol.kind.value != "class":
                continue
            
            for segment_start, segment_end in self._iter_line_windows(
                class_symbol.start_line,
                class_symbol.end_line,
            ):
                start_idx = max(0, segment_start - 1)
                end_idx = min(len(context.lines), segment_end)
                chunk_content = "\n".join(context.lines[start_idx:end_idx])
                linked_entities = self._find_linked_entities(
                    segment_start,
                    segment_end,
                    context.entities,
                )
                chunk = ChunkInfo(
                    chunk_id=self._compute_chunk_id(
                        context.file_path,
                        GranularityLevel.MEDIUM.value,
                        chunk_idx,
                    ),
                    file_path=context.file_path,
                    content=chunk_content,
                    granularity_level=GranularityLevel.MEDIUM.value,
                    span_start=segment_start,
                    span_end=segment_end,
                    entity_ids=tuple(linked_entities),
                )
                chunks.append(chunk)
                chunk_idx += 1
        
        # Group standalone symbols by proximity
        if standalone_symbols:
            sections = self._group_by_proximity(standalone_symbols)
            
            for section in sections:
                if not section:
                    continue
                
                start_line = min(s.start_line for s in section)
                end_line = max(s.end_line for s in section)
                
                for segment_start, segment_end in self._iter_line_windows(
                    start_line,
                    end_line,
                ):
                    start_idx = max(0, segment_start - 1)
                    end_idx = min(len(context.lines), segment_end)
                    chunk_content = "\n".join(context.lines[start_idx:end_idx])

                    linked_entities = self._find_linked_entities(
                        segment_start, segment_end, context.entities
                    )

                    chunk = ChunkInfo(
                        chunk_id=self._compute_chunk_id(
                            context.file_path,
                            GranularityLevel.MEDIUM.value,
                            chunk_idx,
                        ),
                        file_path=context.file_path,
                        content=chunk_content,
                        granularity_level=GranularityLevel.MEDIUM.value,
                        span_start=segment_start,
                        span_end=segment_end,
                        entity_ids=tuple(linked_entities),
                    )
                    chunks.append(chunk)
                    chunk_idx += 1
        
        return chunks
    
    def _create_coarse_chunks(self, context: FileContext) -> list[ChunkInfo]:
        """
        Create coarse-level (file summary) chunks.
        
        Constructed deterministically by concatenating:
        - Module docstring
        - Class / function signatures (no bodies)
        
        No inference, no LLM.
        """
        summary_parts = []
        
        # Extract module docstring (first string literal at file start)
        module_docstring = self._extract_module_docstring(context)
        if module_docstring:
            summary_parts.append(module_docstring)
        
        # Extract signatures
        for symbol in context.symbols:
            if symbol.signature:
                if symbol.kind.value == "class":
                    summary_parts.append(f"class {symbol.name}:")
                elif symbol.kind.value in ["function", "method"]:
                    summary_parts.append(f"def {symbol.signature}:")
        
        if not summary_parts:
            return []
        
        summary_lines = "\n".join(summary_parts).split("\n")

        # All entities are linked to coarse chunks.
        all_entity_ids = [e.entity_id for e in context.entities]
        chunks: list[ChunkInfo] = []
        for idx, offset in enumerate(range(0, len(summary_lines), self.chunk_max_lines)):
            segment_lines = summary_lines[offset : offset + self.chunk_max_lines]
            chunk_content = "\n".join(segment_lines).rstrip()
            if not chunk_content:
                continue
            chunk = ChunkInfo(
                chunk_id=self._compute_chunk_id(
                    context.file_path,
                    GranularityLevel.COARSE.value,
                    idx,
                ),
                file_path=context.file_path,
                content=chunk_content,
                granularity_level=GranularityLevel.COARSE.value,
                span_start=1,
                span_end=len(context.lines),
                entity_ids=tuple(all_entity_ids),
            )
            chunks.append(chunk)

        return chunks
    
    def _extract_module_docstring(self, context: FileContext) -> Optional[str]:
        """
        Extract module-level docstring.
        
        The module docstring is the first statement if it's a string literal.
        """
        # Look for first non-empty, non-comment line
        for i, line in enumerate(context.lines[:10]):  # Check first 10 lines
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            
            # Check for docstring patterns
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # Find the end of the docstring
                quote = stripped[:3]
                if stripped.count(quote) >= 2:
                    # Single-line docstring
                    return stripped[3:stripped.rfind(quote)]
                else:
                    # Multi-line docstring
                    docstring_lines = [stripped[3:]]
                    for j in range(i + 1, min(i + 50, len(context.lines))):
                        end_line = context.lines[j]
                        if quote in end_line:
                            docstring_lines.append(end_line[:end_line.find(quote)])
                            return "\n".join(docstring_lines)
                        docstring_lines.append(end_line)
            break
        
        return None
    
    def _find_linked_entities(
        self,
        start_line: int,
        end_line: int,
        entities: list[EntityInfo],
    ) -> list[str]:
        """Find entity IDs that overlap with the given line range."""
        linked = []
        for entity in entities:
            if (entity.span_start <= end_line and entity.span_end >= start_line):
                linked.append(entity.entity_id)
        return linked
    
    def _group_by_proximity(
        self,
        symbols: list[SymbolInfo],
        max_gap: int = 3,
    ) -> list[list[SymbolInfo]]:
        """
        Group symbols by line proximity.
        
        Symbols separated by more than max_gap blank lines are in different groups.
        """
        if not symbols:
            return []
        
        # Sort by start line
        sorted_symbols = sorted(symbols, key=lambda s: s.start_line)
        
        groups = []
        current_group = [sorted_symbols[0]]
        
        for symbol in sorted_symbols[1:]:
            prev_end = current_group[-1].end_line
            gap = symbol.start_line - prev_end
            
            if gap > max_gap:
                groups.append(current_group)
                current_group = [symbol]
            else:
                current_group.append(symbol)
        
        if current_group:
            groups.append(current_group)
        
        return groups

    def _iter_line_windows(
        self,
        start_line: int,
        end_line: int,
        max_lines: Optional[int] = None,
    ):
        """Yield deterministic contiguous line windows capped by max_lines."""
        window = max(1, int(max_lines if max_lines is not None else self.chunk_max_lines))
        cursor = max(1, int(start_line))
        final = max(cursor, int(end_line))
        while cursor <= final:
            segment_end = min(final, cursor + window - 1)
            yield cursor, segment_end
            cursor = segment_end + 1

    def _fit_fine_prefix(self, prefix_lines: list[str]) -> list[str]:
        """Trim fine-chunk prefix so at least one body line fits inside chunk_max_lines."""
        expanded_prefix: list[str] = []
        for line in prefix_lines:
            expanded_prefix.extend(str(line).split("\n"))

        max_prefix_lines = max(0, self.chunk_max_lines - 1)
        if len(expanded_prefix) <= max_prefix_lines:
            return expanded_prefix
        if max_prefix_lines == 0:
            return []

        header = expanded_prefix[0] if expanded_prefix else ""
        scopes = [line for line in expanded_prefix[1:] if line]
        scope_budget = max(0, max_prefix_lines - 1)
        kept_scopes = scopes[-scope_budget:] if scope_budget > 0 else []
        fitted = [header]
        fitted.extend(kept_scopes)
        if len(fitted) > max_prefix_lines:
            fitted = fitted[-max_prefix_lines:]
        return fitted
