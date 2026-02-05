"""Extended entity extraction for entity-centric indexing.

This module extracts entities beyond basic functions/classes:
- Variables (module-level and class-level)
- Decorators (standalone)
- Imports / aliases
- Config constants
- Type aliases (optional, flag-gated)

Entity Extraction Principles:
- Tree-Sitter + rules only (no LLM)
- Deterministic extraction (fixed queries)
- Each entity has a stable hash ID
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tree_sitter import Node

from homllm.common.config import EntityConfidenceConfig, IndexerConfig
from homllm.common.types import EntityInfo, GranularityLevel, SymbolKind
from homllm.indexer.confidence_scorer import (
    ConfidenceInputs,
    compute_docstring_hash,
    compute_entity_confidence,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractionContext:
    """Context for entity extraction."""
    
    file_path: str
    file_id: str
    content: str
    lines: list[str]
    exports: set[str]  # Names in __all__
    config: IndexerConfig


class EntityExtractor:
    """
    Extended entity extractor for entity-centric indexing.
    
    Extracts entities beyond functions/classes, including:
    - Imports and aliases
    - Module-level variables
    - Config constants (UPPER_CASE convention)
    - Type aliases (optional, flag-gated)
    
    All extraction is deterministic using Tree-Sitter queries.
    """
    
    def __init__(self, config: IndexerConfig):
        """
        Initialize entity extractor.
        
        Args:
            config: Indexer configuration with entity-centric settings
        """
        self.config = config
    
    def extract_entities(
        self,
        root: Node,
        content: str,
        file_path: str,
    ) -> list[EntityInfo]:
        """
        Extract all entities from a parsed file.
        
        Args:
            root: Tree-Sitter root node
            content: File content
            file_path: Path to the file
            
        Returns:
            List of extracted EntityInfo objects
        """
        file_id = self._compute_file_id(file_path)
        lines = content.split("\n")
        exports = self._extract_all_exports(root, content)
        
        context = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            content=content,
            lines=lines,
            exports=exports,
            config=self.config,
        )
        
        entities = []
        
        # Extract imports
        entities.extend(self._extract_imports(root, context))
        
        # Extract module-level variables and config constants
        entities.extend(self._extract_variables(root, context))
        
        # Extract type aliases (if enabled)
        if self.config.type_alias_extraction_enabled:
            entities.extend(self._extract_type_aliases(root, context))
        
        return entities
    
    def _compute_file_id(self, file_path: str) -> str:
        """Compute stable file ID from path."""
        return hashlib.sha256(file_path.encode()).hexdigest()[:16]
    
    def _compute_entity_id(self, file_id: str, name: str, line: int) -> str:
        """Compute stable entity ID."""
        key = f"{file_id}:{name}:{line}"
        return hashlib.sha256(key.encode()).hexdigest()[:24]
    
    def _extract_all_exports(self, root: Node, content: str) -> set[str]:
        """
        Extract names from __all__ declaration.
        
        Returns:
            Set of exported names
        """
        exports = set()
        
        for node in self._traverse_tree(root):
            if node.type == "expression_statement":
                # Look for __all__ = [...]
                for child in node.children:
                    if child.type == "assignment":
                        left = child.child_by_field_name("left")
                        if left and content[left.start_byte:left.end_byte] == "__all__":
                            right = child.child_by_field_name("right")
                            if right and right.type == "list":
                                for item in right.children:
                                    if item.type == "string":
                                        # Extract string content (remove quotes)
                                        text = content[item.start_byte:item.end_byte]
                                        name = text.strip("'\"")
                                        exports.add(name)
        
        return exports
    
    def _extract_imports(
        self,
        root: Node,
        context: ExtractionContext,
    ) -> list[EntityInfo]:
        """
        Extract import statements as entities.
        
        Handles:
        - import module
        - import module as alias
        - from module import name
        - from module import name as alias
        """
        entities = []
        
        for node in self._traverse_tree(root):
            if node.type == "import_statement":
                entities.extend(self._handle_import_statement(node, context))
            elif node.type == "import_from_statement":
                entities.extend(self._handle_import_from_statement(node, context))
        
        return entities
    
    def _handle_import_statement(
        self,
        node: Node,
        context: ExtractionContext,
    ) -> list[EntityInfo]:
        """Handle 'import module' or 'import module as alias'."""
        entities = []
        
        for child in node.children:
            if child.type == "dotted_name":
                name = context.content[child.start_byte:child.end_byte]
                entity = self._create_entity(
                    name=name,
                    entity_type=SymbolKind.IMPORT.value,
                    node=node,
                    context=context,
                )
                entities.append(entity)
            elif child.type == "aliased_import":
                # import module as alias
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node and alias_node:
                    alias = context.content[alias_node.start_byte:alias_node.end_byte]
                    entity = self._create_entity(
                        name=alias,
                        entity_type=SymbolKind.ALIAS.value,
                        node=node,
                        context=context,
                    )
                    entities.append(entity)
        
        return entities
    
    def _handle_import_from_statement(
        self,
        node: Node,
        context: ExtractionContext,
    ) -> list[EntityInfo]:
        """Handle 'from module import name' statements."""
        entities = []
        
        for child in node.children:
            if child.type == "dotted_name":
                # The module being imported from
                continue
            elif child.type == "aliased_import":
                # from module import name as alias
                alias_node = child.child_by_field_name("alias")
                if alias_node:
                    alias = context.content[alias_node.start_byte:alias_node.end_byte]
                    entity = self._create_entity(
                        name=alias,
                        entity_type=SymbolKind.ALIAS.value,
                        node=node,
                        context=context,
                    )
                    entities.append(entity)
                else:
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = context.content[name_node.start_byte:name_node.end_byte]
                        entity = self._create_entity(
                            name=name,
                            entity_type=SymbolKind.IMPORT.value,
                            node=node,
                            context=context,
                        )
                        entities.append(entity)
            elif child.type == "identifier":
                # from module import name
                name = context.content[child.start_byte:child.end_byte]
                entity = self._create_entity(
                    name=name,
                    entity_type=SymbolKind.IMPORT.value,
                    node=node,
                    context=context,
                )
                entities.append(entity)
        
        return entities
    
    def _extract_variables(
        self,
        root: Node,
        context: ExtractionContext,
    ) -> list[EntityInfo]:
        """
        Extract module-level variables and config constants.
        
        Config constants are identified by UPPER_CASE naming convention.
        """
        entities = []
        
        for node in self._traverse_tree(root):
            # Only extract top-level assignments (not inside functions/classes)
            if node.type == "expression_statement":
                parent = node.parent
                if parent and parent.type == "module":
                    for child in node.children:
                        if child.type == "assignment":
                            entities.extend(
                                self._handle_assignment(child, context)
                            )
        
        return entities
    
    def _handle_assignment(
        self,
        node: Node,
        context: ExtractionContext,
    ) -> list[EntityInfo]:
        """Handle assignment expression and determine entity type."""
        entities = []
        
        left = node.child_by_field_name("left")
        if not left:
            return entities
        
        # Skip __all__ and __dunder__ variables
        name = context.content[left.start_byte:left.end_byte]
        if name.startswith("__") and name.endswith("__"):
            return entities
        
        # Determine entity type based on naming convention
        if name.isupper() or (name.upper() == name and "_" in name):
            entity_type = SymbolKind.CONFIG_CONSTANT.value
        else:
            entity_type = SymbolKind.VARIABLE.value
        
        # Check for type annotation
        type_node = node.child_by_field_name("type")
        has_type_annotation = type_node is not None
        
        entity = self._create_entity(
            name=name,
            entity_type=entity_type,
            node=node,
            context=context,
            has_type_annotation=has_type_annotation,
        )
        entities.append(entity)
        
        return entities
    
    def _extract_type_aliases(
        self,
        root: Node,
        context: ExtractionContext,
    ) -> list[EntityInfo]:
        """
        Extract type aliases (Python 3.12+ syntax and typing.TypeAlias).
        
        Handles:
        - type Foo = Bar (Python 3.12+)
        - Foo: TypeAlias = Bar
        """
        entities = []
        
        for node in self._traverse_tree(root):
            # Python 3.12+ type alias statement
            if node.type == "type_alias_statement":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = context.content[name_node.start_byte:name_node.end_byte]
                    entity = self._create_entity(
                        name=name,
                        entity_type=SymbolKind.TYPE_ALIAS.value,
                        node=node,
                        context=context,
                    )
                    entities.append(entity)
            
            # typing.TypeAlias pattern: Foo: TypeAlias = Bar
            elif node.type == "expression_statement":
                for child in node.children:
                    if child.type == "assignment":
                        type_node = child.child_by_field_name("type")
                        if type_node:
                            type_text = context.content[
                                type_node.start_byte:type_node.end_byte
                            ]
                            if "TypeAlias" in type_text:
                                left = child.child_by_field_name("left")
                                if left:
                                    name = context.content[
                                        left.start_byte:left.end_byte
                                    ]
                                    entity = self._create_entity(
                                        name=name,
                                        entity_type=SymbolKind.TYPE_ALIAS.value,
                                        node=child,
                                        context=context,
                                    )
                                    entities.append(entity)
        
        return entities
    
    def _create_entity(
        self,
        name: str,
        entity_type: str,
        node: Node,
        context: ExtractionContext,
        has_type_annotation: bool = False,
        docstring: Optional[str] = None,
    ) -> EntityInfo:
        """
        Create an EntityInfo with confidence scoring.
        
        Args:
            name: Entity name
            entity_type: Entity type from SymbolKind
            node: Tree-Sitter node
            context: Extraction context
            has_type_annotation: Whether entity has type hints
            docstring: Optional docstring content
            
        Returns:
            Fully populated EntityInfo
        """
        entity_id = self._compute_entity_id(
            context.file_id, name, node.start_point[0]
        )
        
        # Compute confidence score
        inputs = ConfidenceInputs(
            name=name,
            has_docstring=docstring is not None,
            is_exported=name in context.exports,
            has_type_annotation=has_type_annotation,
        )
        confidence_score = compute_entity_confidence(
            inputs, context.config.entity_confidence
        )
        
        # Compute docstring hash if present
        docstring_hash = None
        if docstring:
            docstring_hash = compute_docstring_hash(docstring)
        
        return EntityInfo(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
            file_path=context.file_path,
            span_start=node.start_point[0] + 1,  # 1-indexed
            span_end=node.end_point[0] + 1,
            docstring_hash=docstring_hash,
            granularity_level=GranularityLevel.FINE.value,
            confidence_score=confidence_score,
            has_type_annotation=has_type_annotation,
            is_exported=name in context.exports,
        )
    
    def _traverse_tree(self, node: Node):
        """Generator to traverse all nodes in the tree."""
        yield node
        for child in node.children:
            yield from self._traverse_tree(child)
