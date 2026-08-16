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

import logging
import re
from collections import defaultdict
from typing import Optional

from tree_sitter import Node

from homllm.common.types import CallEdge, EntityInfo, RelationInfo, RelationType, SymbolInfo
from homllm.indexer.interfaces import ParseResult


logger = logging.getLogger(__name__)

CALL_NODE_TYPES = {"call", "call_expression", "new_expression"}
CALLABLE_SYMBOL_KINDS = {"function", "method"}


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
        # O(1) membership sets backing the lists. The lists keep insertion
        # order (and are sorted before export); the sets make dedup cheap.
        # Without these, ``if relation not in self.relations`` is O(n) per
        # candidate, making full-repo indexing O(relations^2) and effectively
        # unbounded on real repositories (e.g. sympy's 30k+ relations).
        self._edge_set: set[CallEdge] = set()
        self._relation_set: set[RelationInfo] = set()
        self.symbols: dict[str, SymbolInfo] = {}
        self.entities: dict[str, EntityInfo] = {}  # Entity storage (Plan A)
        self.file_contents: dict[str, str] = {}  # file_path -> content
        self.entity_centric_enabled = entity_centric_enabled

    def _add_edge(self, edge: CallEdge) -> None:
        """Append an edge if not already present (O(1) dedup)."""
        if edge not in self._edge_set:
            self._edge_set.add(edge)
            self.edges.append(edge)

    def _add_relation(self, relation: RelationInfo) -> None:
        """Append a relation if not already present (O(1) dedup)."""
        if relation not in self._relation_set:
            self._relation_set.add(relation)
            self.relations.append(relation)

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

    def _build_symbols_by_name(
        self,
        result: ParseResult,
    ) -> dict[str, list[SymbolInfo]]:
        """Build deterministic symbol lookup by name."""
        symbols_by_name: dict[str, list[SymbolInfo]] = defaultdict(list)
        for symbol in result.symbols:
            symbols_by_name[symbol.name].append(symbol)

        for symbols in symbols_by_name.values():
            symbols.sort(key=lambda s: (s.start_line, s.end_line, s.id))

        return dict(symbols_by_name)

    def _iter_ast_nodes(self, root: Node):
        """Iterate AST nodes in pre-order traversal."""
        stack = [root]
        while stack:
            current = stack.pop()
            yield current
            for child in reversed(current.children):
                stack.append(child)

    def _node_text(self, content_bytes: bytes, node: Optional[Node]) -> str:
        """Read node text from source bytes."""
        if node is None:
            return ""
        return content_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )

    def _find_containing_callable(
        self,
        line_number: int,
        callable_symbols: list[SymbolInfo],
    ) -> Optional[SymbolInfo]:
        """Find innermost callable symbol containing a line."""
        candidates = [
            symbol
            for symbol in callable_symbols
            if symbol.start_line <= line_number <= symbol.end_line
        ]
        if not candidates:
            return None

        return min(
            candidates,
            key=lambda s: (s.end_line - s.start_line, s.start_line, s.id),
        )

    def _select_best_candidate(
        self,
        candidates: list[SymbolInfo],
        line_number: int,
    ) -> Optional[SymbolInfo]:
        """Select deterministic symbol candidate near a line."""
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda s: (abs(s.start_line - line_number), s.start_line, s.id),
        )

    def _extract_identifier_name(self, node: Optional[Node], content_bytes: bytes) -> str:
        """Extract identifier-like text from a node."""
        if node is None:
            return ""

        if node.type in {"identifier", "property_identifier", "type_identifier"}:
            return self._node_text(content_bytes, node)

        if node.type in {"attribute", "member_expression"}:
            property_node = node.child_by_field_name("attribute")
            if property_node is None:
                property_node = node.child_by_field_name("property")
            return self._extract_identifier_name(property_node, content_bytes)

        if node.type == "this":
            return "this"

        return ""

    def _extract_constructed_class_name(
        self,
        node: Optional[Node],
        content_bytes: bytes,
    ) -> str:
        """Extract class-like target from assignment RHS constructors."""
        if node is None:
            return ""

        if node.type in CALL_NODE_TYPES:
            constructor = node.child_by_field_name("constructor")
            function = node.child_by_field_name("function")
            return self._extract_identifier_name(constructor or function, content_bytes)

        return self._extract_identifier_name(node, content_bytes)

    def _extract_assignment_type_hint(
        self,
        node: Node,
        content_bytes: bytes,
        class_names: set[str],
    ) -> Optional[tuple[str, str]]:
        """Extract variable-to-class assignment hints from AST nodes."""
        lhs: Optional[Node] = None
        rhs: Optional[Node] = None

        if node.type == "assignment":
            lhs = node.child_by_field_name("left")
            rhs = node.child_by_field_name("right")
        elif node.type == "variable_declarator":
            lhs = node.child_by_field_name("name")
            rhs = node.child_by_field_name("value")
        elif node.type == "assignment_expression":
            lhs = node.child_by_field_name("left")
            rhs = node.child_by_field_name("right")
        else:
            return None

        variable_name = self._extract_identifier_name(lhs, content_bytes)
        class_name = self._extract_constructed_class_name(rhs, content_bytes)

        if not variable_name or not class_name:
            return None

        if class_name not in class_names:
            return None

        return variable_name, class_name

    def _collect_receiver_type_hints(
        self,
        root: Node,
        content_bytes: bytes,
        callable_symbols: list[SymbolInfo],
        class_names: set[str],
    ) -> dict[str, list[tuple[int, str, str]]]:
        """Collect simple receiver class hints per callable scope."""
        receiver_hints: dict[str, list[tuple[int, str, str]]] = defaultdict(list)

        for node in self._iter_ast_nodes(root):
            if node.type not in {"assignment", "variable_declarator", "assignment_expression"}:
                continue

            hint = self._extract_assignment_type_hint(node, content_bytes, class_names)
            if hint is None:
                continue

            line_number = node.start_point[0] + 1
            caller_symbol = self._find_containing_callable(line_number, callable_symbols)
            if caller_symbol is None:
                continue

            variable_name, class_name = hint
            receiver_hints[caller_symbol.id].append(
                (line_number, variable_name, class_name)
            )

        for hints in receiver_hints.values():
            hints.sort(key=lambda h: (h[0], h[1], h[2]))

        return dict(receiver_hints)

    def _extract_call_target(
        self,
        node: Node,
        content_bytes: bytes,
    ) -> tuple[str, Optional[str]]:
        """Extract callee name and optional receiver from call node."""
        function_node = node.child_by_field_name("constructor")
        if function_node is None:
            function_node = node.child_by_field_name("function")
        if function_node is None:
            return "", None

        if function_node.type in {"attribute", "member_expression"}:
            receiver_node = function_node.child_by_field_name("object")
            attribute_node = function_node.child_by_field_name("attribute")
            if attribute_node is None:
                attribute_node = function_node.child_by_field_name("property")

            callee_name = self._extract_identifier_name(attribute_node, content_bytes)
            receiver_name = self._node_text(content_bytes, receiver_node).strip()
            return callee_name, receiver_name or None

        callee_name = self._extract_identifier_name(function_node, content_bytes)
        return callee_name, None

    def _resolve_receiver_class(
        self,
        receiver_name: str,
        call_line: int,
        caller_symbol: SymbolInfo,
        receiver_hints: dict[str, list[tuple[int, str, str]]],
        class_symbols_by_name: dict[str, list[SymbolInfo]],
        symbols_by_id: dict[str, SymbolInfo],
    ) -> Optional[SymbolInfo]:
        """Resolve receiver variable to class symbol when possible."""
        if receiver_name in {"self", "this"} and caller_symbol.parent_id:
            parent_symbol = symbols_by_id.get(caller_symbol.parent_id)
            if parent_symbol and parent_symbol.kind.value == "class":
                return parent_symbol

        if receiver_name in class_symbols_by_name:
            return self._select_best_candidate(class_symbols_by_name[receiver_name], call_line)

        for hint_line, variable_name, class_name in reversed(
            receiver_hints.get(caller_symbol.id, [])
        ):
            if hint_line > call_line or variable_name != receiver_name:
                continue
            class_candidates = class_symbols_by_name.get(class_name, [])
            return self._select_best_candidate(class_candidates, call_line)

        return None

    def _resolve_callee_symbol(
        self,
        callee_name: str,
        receiver_name: Optional[str],
        call_line: int,
        caller_symbol: SymbolInfo,
        symbols_by_name: dict[str, list[SymbolInfo]],
        class_symbols_by_name: dict[str, list[SymbolInfo]],
        receiver_hints: dict[str, list[tuple[int, str, str]]],
        symbols_by_id: dict[str, SymbolInfo],
    ) -> Optional[SymbolInfo]:
        """Resolve best callee symbol for a call site."""
        candidates = symbols_by_name.get(callee_name, [])
        if not candidates:
            return None

        if receiver_name:
            receiver_class = self._resolve_receiver_class(
                receiver_name,
                call_line,
                caller_symbol,
                receiver_hints,
                class_symbols_by_name,
                symbols_by_id,
            )
            if receiver_class:
                class_scoped = [
                    symbol
                    for symbol in candidates
                    if symbol.parent_id == receiver_class.id
                ]
                if class_scoped:
                    return self._select_best_candidate(class_scoped, call_line)

            method_candidates = [symbol for symbol in candidates if symbol.parent_id]
            if method_candidates:
                return self._select_best_candidate(method_candidates, call_line)

        local_nested = [
            symbol
            for symbol in candidates
            if symbol.parent_id == caller_symbol.id
        ]
        if local_nested:
            return self._select_best_candidate(local_nested, call_line)

        sibling_scope = [
            symbol
            for symbol in candidates
            if symbol.parent_id == caller_symbol.parent_id
        ]
        if sibling_scope:
            return self._select_best_candidate(sibling_scope, call_line)

        callable_candidates = [
            symbol
            for symbol in candidates
            if symbol.kind.value in CALLABLE_SYMBOL_KINDS
        ]
        if callable_candidates:
            return self._select_best_candidate(callable_candidates, call_line)

        return self._select_best_candidate(candidates, call_line)

    def _extract_call_edges_ast(
        self,
        result: ParseResult,
        symbols_by_name: dict[str, list[SymbolInfo]],
    ) -> None:
        """Extract call graph edges via AST traversal."""
        if not result.tree:
            return

        content_bytes = result.content.encode("utf-8")
        callable_symbols = [
            symbol
            for symbol in result.symbols
            if symbol.kind.value in CALLABLE_SYMBOL_KINDS
        ]
        if not callable_symbols:
            return

        symbols_by_id = {symbol.id: symbol for symbol in result.symbols}

        class_symbols_by_name: dict[str, list[SymbolInfo]] = defaultdict(list)
        for symbol in result.symbols:
            if symbol.kind.value == "class":
                class_symbols_by_name[symbol.name].append(symbol)
        for class_symbols in class_symbols_by_name.values():
            class_symbols.sort(key=lambda s: (s.start_line, s.end_line, s.id))

        receiver_hints = self._collect_receiver_type_hints(
            result.tree.root_node,
            content_bytes,
            callable_symbols,
            set(class_symbols_by_name.keys()),
        )

        for node in self._iter_ast_nodes(result.tree.root_node):
            if node.type not in CALL_NODE_TYPES:
                continue

            line_number = node.start_point[0] + 1
            caller_symbol = self._find_containing_callable(line_number, callable_symbols)
            if caller_symbol is None:
                continue

            callee_name, receiver_name = self._extract_call_target(node, content_bytes)
            if not callee_name:
                continue

            callee_symbol = self._resolve_callee_symbol(
                callee_name,
                receiver_name,
                line_number,
                caller_symbol,
                symbols_by_name,
                class_symbols_by_name,
                receiver_hints,
                symbols_by_id,
            )
            if callee_symbol is None:
                continue

            if callee_symbol.id == caller_symbol.id:
                continue

            edge = CallEdge(
                caller_id=caller_symbol.id,
                callee_id=callee_symbol.id,
                call_site_line=line_number,
            )
            self._add_edge(edge)

    def _extract_call_edges_regex(
        self,
        result: ParseResult,
        symbols_by_name: dict[str, list[SymbolInfo]],
    ) -> None:
        """
        Fallback call graph extraction using regex.

        This path is retained for resilience when AST extraction fails.
        """
        content = result.content
        lines = content.split("\n")

        # For each function, find calls to other functions
        for symbol in result.symbols:
            if symbol.kind.value not in CALLABLE_SYMBOL_KINDS:
                continue

            # Get function body (lines between start and end)
            start_idx = max(0, symbol.start_line - 1)
            end_idx = min(len(lines), symbol.end_line)

            # Extract function body
            body_lines = lines[start_idx:end_idx]
            body_text = "\n".join(body_lines)

            # Find function calls (simplified: look for identifier( pattern)
            # This is a basic heuristic; full AST analysis would be more accurate
            for callee_name, callee_candidates in symbols_by_name.items():
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

                    callee_symbol = self._select_best_candidate(
                        callee_candidates,
                        line_num,
                    )
                    if callee_symbol is None or callee_symbol.id == symbol.id:
                        continue

                    edge = CallEdge(
                        caller_id=symbol.id,
                        callee_id=callee_symbol.id,
                        call_site_line=line_num,
                    )
                    # Avoid duplicates (O(1) membership via set)
                    self._add_edge(edge)

    def _extract_call_edges(self, file_path: str, result: ParseResult) -> None:
        """Extract call graph edges using AST first, regex fallback."""
        symbols_by_name = self._build_symbols_by_name(result)
        if not symbols_by_name:
            return

        if result.tree:
            try:
                self._extract_call_edges_ast(result, symbols_by_name)
                return
            except Exception as exc:
                logger.warning(
                    "AST call extraction failed for %s (%s); using regex fallback",
                    file_path,
                    exc,
                )

        self._extract_call_edges_regex(result, symbols_by_name)

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
                self._add_relation(relation)

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
        # Build a single alternation regex over every symbol name so each
        # function body is scanned once instead of once per candidate name.
        # Without this, files with ~2k symbols (e.g. sympy's generated rubi
        # rules) trigger ~4M regex passes per file and full-repo indexing
        # becomes unbounded.
        if not result.symbols:
            return
        symbol_by_name: dict[str, SymbolInfo] = {}
        for ref_symbol in result.symbols:
            symbol_by_name.setdefault(ref_symbol.name, ref_symbol)
        if len(symbol_by_name) == 1:
            return
        names = sorted(symbol_by_name)
        combined = re.compile(rf"\b(?:{'|'.join(re.escape(name) for name in names)})\b")

        for symbol in result.symbols:
            if symbol.kind.value not in ["function", "method"]:
                continue

            # Get function body
            start_idx = max(0, symbol.start_line - 1)
            end_idx = min(len(lines), symbol.end_line)
            body_text = "\n".join(lines[start_idx:end_idx])

            # Find references to other symbols with a single scan
            seen: set[str] = set()
            for match in combined.finditer(body_text):
                name = match.group(0)
                if name == symbol.name or name in seen:
                    continue
                seen.add(name)
                ref_symbol = symbol_by_name[name]
                relation = RelationInfo(
                    src_entity_id=symbol.id,
                    dst_entity_id=ref_symbol.id,
                    relation_type=RelationType.USES.value,
                    extraction_source="identifier_reference",
                )
                self._add_relation(relation)

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
                                self._add_relation(relation)
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
                self._add_relation(relation)

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
                                    self._add_relation(override_rel)

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
            self._add_relation(relation)
        
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

