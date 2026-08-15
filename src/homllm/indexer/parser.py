"""Code parser implementation using Tree-Sitter."""

import ast
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


class _PythonAstNode:
    """Small tree-sitter-like node wrapper backed by Python's stdlib AST."""

    def __init__(
        self,
        node_type: str,
        *,
        start_point: tuple[int, int],
        end_point: tuple[int, int],
        start_byte: int,
        end_byte: int,
        children: list["_PythonAstNode"] | None = None,
        fields: dict[str, "_PythonAstNode"] | None = None,
    ) -> None:
        self.type = node_type
        self.start_point = start_point
        self.end_point = end_point
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.children = children or []
        self._fields = fields or {}
        self.parent = None
        self.prev_sibling = None
        for index, child in enumerate(self.children):
            child.parent = self
            child.prev_sibling = self.children[index - 1] if index > 0 else None

    def child_by_field_name(self, name: str):
        return self._fields.get(name)


class _PythonAstTree:
    def __init__(self, root_node: _PythonAstNode) -> None:
        self.root_node = root_node


class _PythonAstParser:
    """Fallback parser used when tree-sitter language packages are unavailable."""

    def parse(self, content: bytes) -> _PythonAstTree:
        source = content.decode("utf-8", errors="replace")
        return _PythonAstTree(_PythonAstNodeBuilder(source).build())


class _PythonAstNodeBuilder:
    def __init__(self, source: str) -> None:
        self.source = source
        self.lines = source.splitlines(keepends=True)
        self.line_offsets: list[int] = []
        offset = 0
        for line in self.lines:
            self.line_offsets.append(offset)
            offset += len(line.encode("utf-8"))
        if not self.line_offsets:
            self.line_offsets.append(0)

    def build(self) -> _PythonAstNode:
        module = ast.parse(self.source)
        children = [self._wrap(stmt) for stmt in module.body]
        end_byte = len(self.source.encode("utf-8"))
        return _PythonAstNode(
            "module",
            start_point=(0, 0),
            end_point=self._point_from_offset(end_byte),
            start_byte=0,
            end_byte=end_byte,
            children=children,
        )

    def _wrap(self, node: ast.AST) -> _PythonAstNode:
        if isinstance(node, ast.FunctionDef):
            name_node = self._identifier_on_line(node.lineno, node.name, node.col_offset)
            params_node = self._span_node("parameters", node.lineno, node.col_offset, node.lineno, node.col_offset)
            body_node = self._block_node(node.body)
            return self._node(
                "function_definition",
                node,
                children=[name_node, params_node, body_node],
                fields={"name": name_node, "parameters": params_node, "body": body_node},
            )

        if isinstance(node, ast.ClassDef):
            name_node = self._identifier_on_line(node.lineno, node.name, node.col_offset)
            body_node = self._block_node(node.body)
            return self._node(
                "class_definition",
                node,
                children=[name_node, body_node],
                fields={"name": name_node, "body": body_node},
            )

        if isinstance(node, ast.Assign):
            left = self._wrap_expr(node.targets[0])
            right = self._wrap_expr(node.value)
            return self._node(
                "assignment",
                node,
                children=[left, right],
                fields={"left": left, "right": right},
            )

        if isinstance(node, ast.ImportFrom):
            return self._import_from_node(node)

        if isinstance(node, ast.Import):
            return self._import_node(node)

        if isinstance(node, ast.Expr):
            child = self._wrap_expr(node.value)
            return self._node("expression_statement", node, children=[child])

        return self._generic_node(node)

    def _wrap_expr(self, node: ast.AST) -> _PythonAstNode:
        if isinstance(node, ast.Call):
            function = self._wrap_expr(node.func)
            args = [self._wrap_expr(arg) for arg in node.args]
            return self._node(
                "call",
                node,
                children=[function, *args],
                fields={"function": function},
            )

        if isinstance(node, ast.Attribute):
            obj = self._wrap_expr(node.value)
            attr = self._attribute_identifier(node)
            return self._node(
                "attribute",
                node,
                children=[obj, attr],
                fields={"object": obj, "attribute": attr},
            )

        if isinstance(node, ast.Name):
            return self._node("identifier", node)

        if isinstance(node, ast.Constant):
            return self._node("string" if isinstance(node.value, str) else "literal", node)

        return self._generic_node(node)

    def _generic_node(self, node: ast.AST) -> _PythonAstNode:
        children: list[_PythonAstNode] = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                children.append(self._wrap_expr(child))
            elif isinstance(child, ast.stmt):
                children.append(self._wrap(child))
        return self._node(type(node).__name__.lower(), node, children=children)

    def _import_node(self, node: ast.Import) -> _PythonAstNode:
        children = []
        for alias in node.names:
            if alias.asname:
                name_node = self._identifier_on_line(node.lineno, alias.name, node.col_offset, "dotted_name")
                alias_node = self._identifier_on_line(node.lineno, alias.asname, node.col_offset)
                children.append(
                    self._span_node(
                        "aliased_import",
                        node.lineno,
                        node.col_offset,
                        node.end_lineno or node.lineno,
                        node.end_col_offset or node.col_offset,
                        children=[name_node, alias_node],
                        fields={"name": name_node, "alias": alias_node},
                    )
                )
            else:
                children.append(self._identifier_on_line(node.lineno, alias.name, node.col_offset, "dotted_name"))
        return self._node("import_statement", node, children=children)

    def _import_from_node(self, node: ast.ImportFrom) -> _PythonAstNode:
        module_ref = "." * int(node.level or 0) + (node.module or "")
        module_node = self._identifier_on_line(node.lineno, module_ref, node.col_offset, "dotted_name")
        children = [module_node] if module_ref else []
        for alias in node.names:
            if alias.asname:
                name_node = self._identifier_on_line(node.lineno, alias.name, node.col_offset)
                alias_node = self._identifier_on_line(node.lineno, alias.asname, node.col_offset)
                children.append(
                    self._span_node(
                        "aliased_import",
                        node.lineno,
                        node.col_offset,
                        node.end_lineno or node.lineno,
                        node.end_col_offset or node.col_offset,
                        children=[name_node, alias_node],
                        fields={"name": name_node, "alias": alias_node},
                    )
                )
            else:
                children.append(self._identifier_on_line(node.lineno, alias.name, node.col_offset))
        return self._node(
            "import_from_statement",
            node,
            children=children,
            fields={"module_name": module_node} if module_ref else {},
        )

    def _block_node(self, statements: list[ast.stmt]) -> _PythonAstNode:
        children = [self._wrap(stmt) for stmt in statements]
        if children:
            return _PythonAstNode(
                "block",
                start_point=children[0].start_point,
                end_point=children[-1].end_point,
                start_byte=children[0].start_byte,
                end_byte=children[-1].end_byte,
                children=children,
            )
        return _PythonAstNode("block", start_point=(0, 0), end_point=(0, 0), start_byte=0, end_byte=0)

    def _node(
        self,
        node_type: str,
        node: ast.AST,
        *,
        children: list[_PythonAstNode] | None = None,
        fields: dict[str, _PythonAstNode] | None = None,
    ) -> _PythonAstNode:
        lineno = getattr(node, "lineno", 1)
        col = getattr(node, "col_offset", 0)
        end_lineno = getattr(node, "end_lineno", lineno) or lineno
        end_col = getattr(node, "end_col_offset", col) or col
        return self._span_node(node_type, lineno, col, end_lineno, end_col, children=children, fields=fields)

    def _span_node(
        self,
        node_type: str,
        lineno: int,
        col: int,
        end_lineno: int,
        end_col: int,
        *,
        children: list[_PythonAstNode] | None = None,
        fields: dict[str, _PythonAstNode] | None = None,
    ) -> _PythonAstNode:
        start_byte = self._offset(lineno, col)
        end_byte = self._offset(end_lineno, end_col)
        return _PythonAstNode(
            node_type,
            start_point=(lineno - 1, col),
            end_point=(end_lineno - 1, end_col),
            start_byte=start_byte,
            end_byte=end_byte,
            children=children,
            fields=fields,
        )

    def _identifier_on_line(
        self,
        lineno: int,
        text: str,
        start_col: int,
        node_type: str = "identifier",
    ) -> _PythonAstNode:
        line = self.lines[lineno - 1] if lineno - 1 < len(self.lines) else ""
        col = line.find(text, start_col)
        if col < 0:
            col = line.find(text)
        if col < 0:
            col = start_col
        return self._span_node(node_type, lineno, col, lineno, col + len(text))

    def _attribute_identifier(self, node: ast.Attribute) -> _PythonAstNode:
        end_lineno = node.end_lineno or node.lineno
        end_col = node.end_col_offset or node.col_offset
        col = max(node.col_offset, end_col - len(node.attr))
        return self._span_node("identifier", end_lineno, col, end_lineno, col + len(node.attr))

    def _offset(self, lineno: int, col: int) -> int:
        line_index = max(0, lineno - 1)
        base = self.line_offsets[line_index] if line_index < len(self.line_offsets) else len(self.source.encode("utf-8"))
        return base + len((self.lines[line_index][:col] if line_index < len(self.lines) else "").encode("utf-8"))

    def _point_from_offset(self, offset: int) -> tuple[int, int]:
        running = 0
        for index, line in enumerate(self.lines):
            next_offset = running + len(line.encode("utf-8"))
            if offset <= next_offset:
                return index, offset - running
            running = next_offset
        return max(0, len(self.lines) - 1), 0


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
            self.parsers["python"] = _PythonAstParser()

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
