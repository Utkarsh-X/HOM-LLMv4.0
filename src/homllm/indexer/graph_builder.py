"""Structural graph builder for call graphs, import graphs, etc.

Extended for entity-centric indexing (Plan A) with typed relations:
- calls: Function/method calls
- defines: Entity definitions (what a scope defines)
- uses: Symbol usage (references within a scope)
- imports: Import relationships
- inherits: Class inheritance
- overrides: Method overrides (optional)
- type_annotates: Type annotation links (optional)
"""

import re
from typing import Optional

from tree_sitter import Node

from homllm.common.types import CallEdge, EntityInfo, RelationInfo, RelationType, SymbolInfo
from homllm.indexer.interfaces import ParseResult


class GraphBuilder:
    """
    Builds structural graphs from parsed symbols.
    
    Extended for entity-centric indexing with typed relations.
    """

    def __init__(self, entity_centric_enabled: bool = True):
        """
        Initialize graph builder.
        
        Args:
            entity_centric_enabled: Whether to extract typed relations
        """
        self.edges: list[CallEdge] = []
        self.relations: list[RelationInfo] = []  # Typed relations (Plan A)
        self.symbols: dict[str, SymbolInfo] = {}
        self.entities: dict[str, EntityInfo] = {}  # Entity storage (Plan A)
        self.file_contents: dict[str, str] = {}  # file_path -> content
        self.entity_centric_enabled = entity_centric_enabled

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
        
        # Extract typed relations if entity-centric indexing is enabled
        if self.entity_centric_enabled:
            self._extract_typed_relations(file_path, result)

    def add_entities(self, entities: list[EntityInfo]) -> None:
        """
        Add extracted entities for relation extraction.
        
        Args:
            entities: List of EntityInfo from entity extractor
        """
        for entity in entities:
            self.entities[entity.entity_id] = entity

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

    def _extract_typed_relations(self, file_path: str, result: ParseResult) -> None:
        """
        Extract typed relations for entity-centric indexing.
        
        Relation Types:
        - defines: What entities a scope defines
        - uses: What symbols are used within a scope
        - imports: Import relationships
        - inherits: Class inheritance
        """
        content = result.content
        lines = content.split("\n")
        
        # Extract defines relations
        self._extract_defines_relations(result)
        
        # Extract uses relations
        self._extract_uses_relations(result, content, lines)
        
        # Extract inherits relations
        self._extract_inherits_relations(result, content)

    def _extract_defines_relations(self, result: ParseResult) -> None:
        """
        Extract 'defines' relations: what a scope defines.
        
        Examples:
        - Module defines functions, classes, variables
        - Class defines methods
        - Function defines local variables (optional)
        """
        for symbol in result.symbols:
            if symbol.parent_id:
                # This symbol is defined by its parent
                relation = RelationInfo(
                    src_entity_id=symbol.parent_id,
                    dst_entity_id=symbol.id,
                    relation_type=RelationType.DEFINES.value,
                    extraction_source="symbol_parent",
                )
                if relation not in self.relations:
                    self.relations.append(relation)

    def _extract_uses_relations(
        self,
        result: ParseResult,
        content: str,
        lines: list[str],
    ) -> None:
        """
        Extract 'uses' relations: what symbols are referenced.
        
        Uses regex matching to find symbol references in function bodies.
        """
        # Build symbol name set
        symbol_names = {s.name: s for s in result.symbols}
        
        for symbol in result.symbols:
            if symbol.kind.value not in ["function", "method"]:
                continue
            
            # Get function body
            start_idx = max(0, symbol.start_line - 1)
            end_idx = min(len(lines), symbol.end_line)
            body_text = "\n".join(lines[start_idx:end_idx])
            
            # Find references to other symbols
            for name, ref_symbol in symbol_names.items():
                if name == symbol.name:
                    continue
                
                # Look for identifier usage (not just calls)
                pattern = rf"\b{re.escape(name)}\b"
                if re.search(pattern, body_text):
                    relation = RelationInfo(
                        src_entity_id=symbol.id,
                        dst_entity_id=ref_symbol.id,
                        relation_type=RelationType.USES.value,
                        extraction_source="identifier_reference",
                    )
                    if relation not in self.relations:
                        self.relations.append(relation)

    def _extract_inherits_relations(self, result: ParseResult, content: str) -> None:
        """
        Extract 'inherits' relations: class inheritance.
        
        Parses class definitions to find base classes.
        """
        for symbol in result.symbols:
            if symbol.kind.value != "class":
                continue
            
            # Find base classes in signature
            if symbol.signature:
                # Pattern: class Name(Base1, Base2)
                match = re.search(r"\(([^)]+)\)", symbol.signature)
                if match:
                    bases = match.group(1).split(",")
                    for base in bases:
                        base_name = base.strip()
                        if not base_name or base_name in ["object", "ABC"]:
                            continue
                        
                        # Find base class in symbols
                        for s in result.symbols:
                            if s.name == base_name and s.kind.value == "class":
                                relation = RelationInfo(
                                    src_entity_id=symbol.id,
                                    dst_entity_id=s.id,
                                    relation_type=RelationType.INHERITS.value,
                                    extraction_source="class_definition",
                                )
                                if relation not in self.relations:
                                    self.relations.append(relation)
                                break

    def extract_import_relations(
        self,
        entities: list[EntityInfo],
        file_path: str,
    ) -> None:
        """
        Extract 'imports' relations from entity data.
        
        Links import entities to the module they import.
        
        Args:
            entities: Extracted entities including imports
            file_path: Path to the file
        """
        for entity in entities:
            if entity.entity_type in ["import", "alias"]:
                # Create relation from file to imported entity
                # Note: dst_entity_id would ideally reference the actual module
                # For now, we use the import entity itself
                relation = RelationInfo(
                    src_entity_id=f"file:{file_path}",
                    dst_entity_id=entity.entity_id,
                    relation_type=RelationType.IMPORTS.value,
                    extraction_source="import_statement",
                )
                if relation not in self.relations:
                    self.relations.append(relation)

    def extract_override_relations(
        self,
        result: ParseResult,
        content: str,
    ) -> None:
        """
        Extract 'overrides' relations: method overrides base class.
        
        This is an optional relation type with low cost, high ROI.
        Identifies methods that override parent class methods.
        """
        # Group symbols by parent
        class_methods: dict[str, list[SymbolInfo]] = {}
        
        for symbol in result.symbols:
            if symbol.kind.value == "method" and symbol.parent_id:
                if symbol.parent_id not in class_methods:
                    class_methods[symbol.parent_id] = []
                class_methods[symbol.parent_id].append(symbol)
        
        # For each class, check if methods override parent methods
        for class_id, methods in class_methods.items():
            class_symbol = self.symbols.get(class_id)
            if not class_symbol:
                continue
            
            # Find inherited methods (from INHERITS relations)
            inherited_methods = set()
            for relation in self.relations:
                if (relation.src_entity_id == class_id and 
                    relation.relation_type == RelationType.INHERITS.value):
                    parent_id = relation.dst_entity_id
                    parent_methods = class_methods.get(parent_id, [])
                    for pm in parent_methods:
                        inherited_methods.add(pm.name)
            
            # Check for overrides
            for method in methods:
                if method.name in inherited_methods:
                    # Find the parent method
                    for relation in self.relations:
                        if (relation.src_entity_id == class_id and
                            relation.relation_type == RelationType.INHERITS.value):
                            parent_id = relation.dst_entity_id
                            for pm in class_methods.get(parent_id, []):
                                if pm.name == method.name:
                                    override_rel = RelationInfo(
                                        src_entity_id=method.id,
                                        dst_entity_id=pm.id,
                                        relation_type=RelationType.OVERRIDES.value,
                                        extraction_source="method_override",
                                    )
                                    if override_rel not in self.relations:
                                        self.relations.append(override_rel)

    def build_call_graph(self) -> list[CallEdge]:
        """
        Build call graph edges from collected symbols.
        
        Returns:
            List of call edges (caller_id, callee_id, call_site_line)
        """
        # Sort edges for determinism
        self.edges.sort(key=lambda e: (e.caller_id, e.callee_id, e.call_site_line))
        return self.edges

    def build_relation_graph(self) -> list[RelationInfo]:
        """
        Build typed relation graph from collected data.
        
        Returns:
            List of typed relations sorted for determinism
        """
        # Add CALLS relations from call edges
        for edge in self.edges:
            relation = RelationInfo(
                src_entity_id=edge.caller_id,
                dst_entity_id=edge.callee_id,
                relation_type=RelationType.CALLS.value,
                extraction_source="call_expression",
            )
            if relation not in self.relations:
                self.relations.append(relation)
        
        # Sort for determinism
        self.relations.sort(
            key=lambda r: (r.src_entity_id, r.dst_entity_id, r.relation_type)
        )
        return self.relations

    def get_all_symbols(self) -> list[SymbolInfo]:
        """Get all collected symbols, sorted for determinism."""
        symbols = list(self.symbols.values())
        symbols.sort(key=lambda s: (s.file, s.start_line, s.name))
        return symbols

    def get_all_entities(self) -> list[EntityInfo]:
        """Get all collected entities, sorted for determinism."""
        entities = list(self.entities.values())
        entities.sort(key=lambda e: (e.file_path, e.span_start, e.name))
        return entities

    def validate(self) -> list[str]:
        """
        Validate graph integrity.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        symbol_ids = set(self.symbols.keys())
        entity_ids = set(self.entities.keys())
        all_ids = symbol_ids | entity_ids

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

        # Check for dangling references in relations (warning only for entities)
        for relation in self.relations:
            # Skip file-based source IDs
            if relation.src_entity_id.startswith("file:"):
                continue
            if relation.src_entity_id not in all_ids:
                errors.append(
                    f"Relation references unknown src: {relation.src_entity_id}"
                )

        return errors

