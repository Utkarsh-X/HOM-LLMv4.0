"""Code parser implementation using Tree-Sitter."""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Node, Parser

from homllm.common.types import SymbolInfo, SymbolKind
from homllm.indexer.interfaces import CodeParser, ParseResult

logger = logging.getLogger(__name__)

# Language name mapping
LANGUAGE_MAP = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "tsx": "typescript",
}


class TreeSitterParser(CodeParser):
    """Code parser using Tree-Sitter for AST extraction."""

    def __init__(self):
        """Initialize parser with language support."""
        self.parsers: dict[str, Parser] = {}
        self.languages: dict[str, Language] = {}
        self._init_languages()

    def _init_languages(self) -> None:
        """Initialize Tree-Sitter languages."""
        try:
            from tree_sitter_language_pack import get_language

            for lang_name in ["python", "javascript", "typescript"]:
                try:
                    lang = get_language(lang_name)
                    parser = Parser(lang)
                    self.parsers[lang_name] = parser
                    self.languages[lang_name] = lang
                except Exception as e:
                    logger.warning(f"Failed to load {lang_name} parser: {e}")
        except ImportError:
            logger.warning("tree-sitter-language-pack not available, parsing disabled")

    def parse(self, file_path: Path, language: str) -> ParseResult:
        """
        Returns AST and extracted symbols.
        
        Failure Handling:
        - Parse errors are logged, not raised
        - Unparseable files return ParseResult with parse_error=True
        - Parser crashes are isolated per-file
        """
        try:
            # Read file content
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return ParseResult(
                symbols=[],
                content="",
                parse_error=True,
                error_message=str(e),
            )

        # Normalize language name
        lang_key = LANGUAGE_MAP.get(language.lower(), language.lower())
        if lang_key not in self.parsers:
            logger.warning(f"Unsupported language: {language}")
            return ParseResult(
                symbols=[],
                content=content,
                parse_error=False,
            )

        try:
            # Parse with Tree-Sitter
            parser = self.parsers[lang_key]
            tree = parser.parse(bytes(content, "utf-8"))
            root = tree.root_node

            # Extract symbols based on language
            symbols = []
            if lang_key == "python":
                symbols = self._extract_python_symbols(root, content, str(file_path))
            elif lang_key in ["javascript", "typescript"]:
                symbols = self._extract_js_symbols(root, content, str(file_path))

            return ParseResult(
                symbols=symbols,
                content=content,
                parse_error=False,
                tree=tree,  # Plan A: Include tree for entity extraction
            )
        except Exception as e:
            logger.error(f"Parse error in {file_path}: {e}")
            return ParseResult(
                symbols=[],
                content=content,
                parse_error=True,
                error_message=str(e),
            )

    def _extract_python_symbols(
        self, root: Node, content: str, file_path: str
    ) -> list[SymbolInfo]:
        """Extract symbols from Python AST."""
        symbols = []
        file_id = hashlib.sha256(file_path.encode()).hexdigest()[:16]

        def traverse(node: Node, parent_id: Optional[str] = None) -> None:
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    symbol_id = f"{file_id}:{name}:{node.start_point[0]}"
                    
                    # Extract signature
                    params_node = node.child_by_field_name("parameters")
                    signature = None
                    if params_node:
                        sig_text = content[params_node.start_byte : params_node.end_byte]
                        signature = f"{name}{sig_text}"

                    # Extract decorators
                    decorators = []
                    if node.prev_sibling and node.prev_sibling.type == "decorator":
                        # Check for decorators before function
                        current = node.prev_sibling
                        while current and current.type == "decorator":
                            decorator_text = content[current.start_byte : current.end_byte]
                            decorators.append(decorator_text.strip())
                            current = current.prev_sibling

                    symbols.append(
                        SymbolInfo(
                            id=symbol_id,
                            name=name,
                            kind=SymbolKind.FUNCTION,
                            file=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=signature,
                            decorators=tuple(decorators),
                            parent_id=parent_id,
                        )
                    )
                    # Traverse function body for nested functions
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, symbol_id)

            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    symbol_id = f"{file_id}:{name}:{node.start_point[0]}"
                    
                    symbols.append(
                        SymbolInfo(
                            id=symbol_id,
                            name=name,
                            kind=SymbolKind.CLASS,
                            file=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            parent_id=parent_id,
                        )
                    )
                    # Traverse class body for methods
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, symbol_id)

            else:
                # Traverse children
                for child in node.children:
                    traverse(child, parent_id)

        traverse(root)
        return symbols

    def _extract_js_symbols(
        self, root: Node, content: str, file_path: str
    ) -> list[SymbolInfo]:
        """Extract symbols from JavaScript/TypeScript AST."""
        symbols = []
        file_id = hashlib.sha256(file_path.encode()).hexdigest()[:16]

        def traverse(node: Node, parent_id: Optional[str] = None) -> None:
            if node.type in ["function_declaration", "function"]:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    symbol_id = f"{file_id}:{name}:{node.start_point[0]}"
                    
                    # Extract signature
                    params_node = node.child_by_field_name("parameters")
                    signature = None
                    if params_node:
                        sig_text = content[params_node.start_byte : params_node.end_byte]
                        signature = f"{name}{sig_text}"

                    symbols.append(
                        SymbolInfo(
                            id=symbol_id,
                            name=name,
                            kind=SymbolKind.FUNCTION,
                            file=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=signature,
                            parent_id=parent_id,
                        )
                    )

            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    symbol_id = f"{file_id}:{name}:{node.start_point[0]}"
                    
                    symbols.append(
                        SymbolInfo(
                            id=symbol_id,
                            name=name,
                            kind=SymbolKind.CLASS,
                            file=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            parent_id=parent_id,
                        )
                    )
                    # Traverse class body for methods
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, symbol_id)

            elif node.type == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte : name_node.end_byte]
                    symbol_id = f"{file_id}:{name}:{node.start_point[0]}"
                    
                    symbols.append(
                        SymbolInfo(
                            id=symbol_id,
                            name=name,
                            kind=SymbolKind.METHOD,
                            file=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            parent_id=parent_id,
                        )
                    )

            else:
                # Traverse children
                for child in node.children:
                    traverse(child, parent_id)

        traverse(root)
        return symbols

    def supported_languages(self) -> list[str]:
        """Returns list of parseable languages."""
        return list(self.parsers.keys())
