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
        Create fine-level (symbol-level) chunks.
        
        One chunk per function/method/class.
        """
        chunks = []
        
        for idx, symbol in enumerate(context.symbols):
            # Skip very small symbols (less than 2 lines)
            if symbol.end_line - symbol.start_line < 2:
                continue
            
            # Extract symbol content
            start_idx = max(0, symbol.start_line - 1)
            end_idx = min(len(context.lines), symbol.end_line)
            chunk_content = "\n".join(context.lines[start_idx:end_idx])
            
            # Find linked entity IDs
            linked_entities = self._find_linked_entities(
                symbol.start_line,
                symbol.end_line,
                context.entities,
            )
            
            chunk = ChunkInfo(
                chunk_id=self._compute_chunk_id(
                    context.file_path,
                    GranularityLevel.FINE.value,
                    idx,
                ),
                file_path=context.file_path,
                content=chunk_content,
                granularity_level=GranularityLevel.FINE.value,
                span_start=symbol.start_line,
                span_end=symbol.end_line,
                entity_ids=tuple(linked_entities),
            )
            chunks.append(chunk)
        
        return chunks
    
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
            
            # Extract the entire class
            start_idx = max(0, class_symbol.start_line - 1)
            end_idx = min(len(context.lines), class_symbol.end_line)
            chunk_content = "\n".join(context.lines[start_idx:end_idx])
            
            # Find linked entities
            linked_entities = self._find_linked_entities(
                class_symbol.start_line,
                class_symbol.end_line,
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
                span_start=class_symbol.start_line,
                span_end=class_symbol.end_line,
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
                
                start_idx = max(0, start_line - 1)
                end_idx = min(len(context.lines), end_line)
                chunk_content = "\n".join(context.lines[start_idx:end_idx])
                
                linked_entities = self._find_linked_entities(
                    start_line, end_line, context.entities
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
                    span_start=start_line,
                    span_end=end_line,
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
        
        chunk_content = "\n".join(summary_parts)
        
        # All entities are linked to coarse chunk
        all_entity_ids = [e.entity_id for e in context.entities]
        
        chunk = ChunkInfo(
            chunk_id=self._compute_chunk_id(
                context.file_path,
                GranularityLevel.COARSE.value,
                0,
            ),
            file_path=context.file_path,
            content=chunk_content,
            granularity_level=GranularityLevel.COARSE.value,
            span_start=1,
            span_end=len(context.lines),
            entity_ids=tuple(all_entity_ids),
        )
        
        return [chunk]
    
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
