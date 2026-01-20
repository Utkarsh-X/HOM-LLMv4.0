"""Structural graph builder for call graphs, import graphs, etc."""

import re
from typing import Optional

from homllm.common.types import CallEdge, SymbolInfo
from homllm.indexer.interfaces import ParseResult


class GraphBuilder:
    """Builds structural graphs from parsed symbols."""

    def __init__(self):
        """Initialize graph builder."""
        self.edges: list[CallEdge] = []
        self.symbols: dict[str, SymbolInfo] = {}
        self.file_contents: dict[str, str] = {}  # file_path -> content

    def add_file_result(self, file_path: str, result: ParseResult) -> None:
        """
        Add symbols and extract graph edges from a parsed file.
        
        Graph Invariants:
        - Edges reference only symbol IDs that exist in symbols.json
        - No dangling references (validated at index finalization)
        - Graph is stored as adjacency list, not matrix
        """
        # Store file content for call graph extraction
        self.file_contents[file_path] = result.content

        # Store symbols
        for symbol in result.symbols:
            self.symbols[symbol.id] = symbol

        # Extract call graph edges from this file
        self._extract_call_edges(file_path, result)

    def _extract_call_edges(self, file_path: str, result: ParseResult) -> None:
        """
        Extract call graph edges by analyzing function bodies.
        
        This is a simplified implementation that looks for function calls
        within function definitions. A more sophisticated version would
        use the full AST from the parser.
        """
        content = result.content
        lines = content.split("\n")

        # Build name-to-symbol mapping for this file
        file_symbols: dict[str, SymbolInfo] = {}
        for symbol in result.symbols:
            file_symbols[symbol.name] = symbol

        # For each function, find calls to other functions
        for symbol in result.symbols:
            if symbol.kind.value not in ["function", "method"]:
                continue

            # Get function body (lines between start and end)
            start_idx = max(0, symbol.start_line - 1)
            end_idx = min(len(lines), symbol.end_line)

            # Extract function body
            body_lines = lines[start_idx:end_idx]
            body_text = "\n".join(body_lines)

            # Find function calls (simplified: look for identifier( pattern)
            # This is a basic heuristic; full AST analysis would be more accurate
            for callee_name, callee_symbol in file_symbols.items():
                if callee_name == symbol.name:
                    continue  # Skip self-calls for now

                # Look for function calls in body
                # Pattern: identifier( or identifier.attribute(
                pattern = rf"\b{re.escape(callee_name)}\s*\("
                matches = re.finditer(pattern, body_text)

                for match in matches:
                    # Find line number of match
                    match_pos = match.start()
                    line_num = body_text[:match_pos].count("\n") + symbol.start_line

                    edge = CallEdge(
                        caller_id=symbol.id,
                        callee_id=callee_symbol.id,
                        call_site_line=line_num,
                    )
                    # Avoid duplicates
                    if edge not in self.edges:
                        self.edges.append(edge)

    def build_call_graph(self) -> list[CallEdge]:
        """
        Build call graph edges from collected symbols.
        
        Returns:
            List of call edges (caller_id, callee_id, call_site_line)
        """
        # Sort edges for determinism
        self.edges.sort(key=lambda e: (e.caller_id, e.callee_id, e.call_site_line))
        return self.edges

    def get_all_symbols(self) -> list[SymbolInfo]:
        """Get all collected symbols, sorted for determinism."""
        symbols = list(self.symbols.values())
        symbols.sort(key=lambda s: (s.file, s.start_line, s.name))
        return symbols

    def validate(self) -> list[str]:
        """
        Validate graph integrity.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        symbol_ids = set(self.symbols.keys())

        # Check for dangling references in call edges
        for edge in self.edges:
            if edge.caller_id not in symbol_ids:
                errors.append(
                    f"Call edge references unknown caller: {edge.caller_id}"
                )
            if edge.callee_id not in symbol_ids:
                errors.append(
                    f"Call edge references unknown callee: {edge.callee_id}"
                )

        # Check for symbols with invalid parent_id
        for symbol in self.symbols.values():
            if symbol.parent_id and symbol.parent_id not in symbol_ids:
                errors.append(
                    f"Symbol {symbol.id} has invalid parent_id: {symbol.parent_id}"
                )

        return errors
