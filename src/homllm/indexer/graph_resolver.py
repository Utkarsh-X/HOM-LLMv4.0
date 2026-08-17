"""Symbol resolution for import entities.

Builds hard links from import/alias entities to concrete symbol definitions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from tree_sitter import Node
except ImportError:
    # tree-sitter is optional; Node is only used in type annotations here, so
    # the module imports cleanly when the native dependency is not installed.
    Node = None  # type: ignore[assignment, misc]

from homllm.common.types import EntityInfo, FileInfo, RelationInfo, RelationType, SymbolInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportSpec:
    """Normalized import statement record extracted from AST."""

    file_path: str
    line_number: int
    exposed_name: str
    imported_name: str
    module_ref: str
    import_kind: str


class SymbolResolver:
    """Resolve import entities to symbol definitions."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def extract_import_specs(
        self,
        root: Node,
        content: str,
        file_path: str,
    ) -> list[ImportSpec]:
        """Extract import specs from a parsed Python AST."""
        normalized_path = self._normalize_rel_path(file_path)
        specs: list[ImportSpec] = []

        for node in self._traverse_tree(root):
            if node.type == "import_statement":
                specs.extend(
                    self._extract_import_statement_specs(
                        node,
                        content,
                        normalized_path,
                    )
                )
            elif node.type == "import_from_statement":
                specs.extend(
                    self._extract_import_from_statement_specs(
                        node,
                        content,
                        normalized_path,
                    )
                )

        return specs

    def resolve_import_entities(
        self,
        import_entities: list[EntityInfo],
        symbols: list[SymbolInfo],
        files: list[FileInfo],
        import_specs: list[ImportSpec],
    ) -> list[RelationInfo]:
        """Resolve import entities into hard relation edges."""
        if not import_entities or not symbols or not import_specs:
            return []

        symbols_by_file_and_name = self._build_symbols_by_file_and_name(symbols)
        module_to_files, available_files = self._build_module_to_files(files, symbols)

        specs_by_key: dict[tuple[str, int, str], ImportSpec] = {}
        for spec in import_specs:
            key = (spec.file_path, spec.line_number, spec.exposed_name)
            if key not in specs_by_key:
                specs_by_key[key] = spec

        relations: list[RelationInfo] = []
        seen_edges: set[tuple[str, str, str]] = set()

        for entity in import_entities:
            key = (
                self._normalize_rel_path(entity.file_path),
                entity.span_start,
                entity.name,
            )
            spec = specs_by_key.get(key)
            if spec is None:
                continue

            target_symbol = self._resolve_import_spec(
                spec,
                symbols_by_file_and_name,
                module_to_files,
                available_files,
            )
            if target_symbol is None:
                continue

            edge_key = (
                entity.entity_id,
                target_symbol.id,
                RelationType.RESOLVES_TO.value,
            )
            if edge_key in seen_edges:
                continue

            seen_edges.add(edge_key)
            relations.append(
                RelationInfo(
                    src_entity_id=entity.entity_id,
                    dst_entity_id=target_symbol.id,
                    relation_type=RelationType.RESOLVES_TO.value,
                    extraction_source="symbol_resolution",
                )
            )

        return relations

    def _extract_import_statement_specs(
        self,
        node: Node,
        content: str,
        file_path: str,
    ) -> list[ImportSpec]:
        specs: list[ImportSpec] = []
        line_number = node.start_point[0] + 1

        for child in node.children:
            if child.type == "dotted_name":
                module_name = content[child.start_byte : child.end_byte]
                specs.append(
                    ImportSpec(
                        file_path=file_path,
                        line_number=line_number,
                        exposed_name=module_name,
                        imported_name=module_name,
                        module_ref=module_name,
                        import_kind="import",
                    )
                )
            elif child.type == "aliased_import":
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node is None or alias_node is None:
                    continue

                module_name = content[name_node.start_byte : name_node.end_byte]
                alias_name = content[alias_node.start_byte : alias_node.end_byte]
                specs.append(
                    ImportSpec(
                        file_path=file_path,
                        line_number=line_number,
                        exposed_name=alias_name,
                        imported_name=module_name,
                        module_ref=module_name,
                        import_kind="import",
                    )
                )

        return specs

    def _extract_import_from_statement_specs(
        self,
        node: Node,
        content: str,
        file_path: str,
    ) -> list[ImportSpec]:
        specs: list[ImportSpec] = []
        line_number = node.start_point[0] + 1

        module_node = node.child_by_field_name("module_name")
        module_ref = ""
        module_span: Optional[tuple[int, int]] = None
        if module_node is not None:
            module_ref = content[module_node.start_byte : module_node.end_byte]
            module_span = (module_node.start_byte, module_node.end_byte)

        for child in node.children:
            if child.type == "dotted_name":
                child_span = (child.start_byte, child.end_byte)
                if module_span is not None and child_span == module_span:
                    continue
                imported_name = content[child.start_byte : child.end_byte]
                specs.append(
                    ImportSpec(
                        file_path=file_path,
                        line_number=line_number,
                        exposed_name=imported_name,
                        imported_name=imported_name,
                        module_ref=module_ref,
                        import_kind="from",
                    )
                )
            elif child.type == "identifier":
                imported_name = content[child.start_byte : child.end_byte]
                specs.append(
                    ImportSpec(
                        file_path=file_path,
                        line_number=line_number,
                        exposed_name=imported_name,
                        imported_name=imported_name,
                        module_ref=module_ref,
                        import_kind="from",
                    )
                )
            elif child.type == "aliased_import":
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node is None or alias_node is None:
                    continue
                imported_name = content[name_node.start_byte : name_node.end_byte]
                alias_name = content[alias_node.start_byte : alias_node.end_byte]
                specs.append(
                    ImportSpec(
                        file_path=file_path,
                        line_number=line_number,
                        exposed_name=alias_name,
                        imported_name=imported_name,
                        module_ref=module_ref,
                        import_kind="from",
                    )
                )

        return specs

    def _build_symbols_by_file_and_name(
        self,
        symbols: list[SymbolInfo],
    ) -> dict[tuple[str, str], list[SymbolInfo]]:
        by_file_and_name: dict[tuple[str, str], list[SymbolInfo]] = {}

        for symbol in symbols:
            file_path = self._normalize_rel_path(symbol.file)
            key = (file_path, symbol.name)
            by_file_and_name.setdefault(key, []).append(symbol)

        for symbol_list in by_file_and_name.values():
            symbol_list.sort(
                key=lambda symbol: (
                    symbol.parent_id is not None,
                    symbol.start_line,
                    symbol.id,
                )
            )

        return by_file_and_name

    def _build_module_to_files(
        self,
        files: list[FileInfo],
        symbols: list[SymbolInfo],
    ) -> tuple[dict[str, list[str]], set[str]]:
        available_files = {
            self._normalize_rel_path(str(file_info.path))
            for file_info in files
        }

        if not available_files:
            available_files = {
                self._normalize_rel_path(symbol.file)
                for symbol in symbols
            }

        module_to_files: dict[str, list[str]] = {}
        for file_path in sorted(available_files):
            for module_name in self._module_names_for_file(file_path):
                if not module_name:
                    continue
                module_to_files.setdefault(module_name, []).append(file_path)

        for module_name, module_files in module_to_files.items():
            module_to_files[module_name] = sorted(set(module_files))

        return module_to_files, available_files

    def _resolve_import_spec(
        self,
        spec: ImportSpec,
        symbols_by_file_and_name: dict[tuple[str, str], list[SymbolInfo]],
        module_to_files: dict[str, list[str]],
        available_files: set[str],
    ) -> Optional[SymbolInfo]:
        module_files = self._resolve_module_ref(
            importer_file=spec.file_path,
            module_ref=spec.module_ref,
            module_to_files=module_to_files,
            available_files=available_files,
        )

        if spec.import_kind == "from":
            target_name = spec.imported_name.split(".")[-1]

            for module_file in module_files:
                symbol = self._pick_symbol(symbols_by_file_and_name, module_file, target_name)
                if symbol is not None:
                    return symbol

            nested_module_ref = self._join_module_ref(spec.module_ref, spec.imported_name)
            nested_module_files = self._resolve_module_ref(
                importer_file=spec.file_path,
                module_ref=nested_module_ref,
                module_to_files=module_to_files,
                available_files=available_files,
            )
            for nested_module_file in nested_module_files:
                symbol = self._pick_symbol(
                    symbols_by_file_and_name,
                    nested_module_file,
                    target_name,
                )
                if symbol is not None:
                    return symbol

            return None

        target_module_leaf = spec.imported_name.split(".")[-1]
        for module_file in module_files:
            symbol = self._pick_symbol(
                symbols_by_file_and_name,
                module_file,
                target_module_leaf,
            )
            if symbol is not None:
                return symbol

        return None

    def _pick_symbol(
        self,
        symbols_by_file_and_name: dict[tuple[str, str], list[SymbolInfo]],
        file_path: str,
        symbol_name: str,
    ) -> Optional[SymbolInfo]:
        candidates = symbols_by_file_and_name.get((file_path, symbol_name), [])
        if not candidates:
            return None
        return candidates[0]

    def _resolve_module_ref(
        self,
        importer_file: str,
        module_ref: str,
        module_to_files: dict[str, list[str]],
        available_files: set[str],
    ) -> list[str]:
        resolved_module = self._resolve_module_name(importer_file, module_ref)
        if not resolved_module:
            return []

        if resolved_module in module_to_files:
            return module_to_files[resolved_module]

        path_prefix = resolved_module.replace(".", "/")
        candidates = [
            f"{path_prefix}.py",
            f"{path_prefix}/__init__.py",
        ]
        return [candidate for candidate in candidates if candidate in available_files]

    def _resolve_module_name(self, importer_file: str, module_ref: str) -> str:
        module_ref = module_ref.strip()
        if not module_ref:
            return ""

        relative_level = 0
        while relative_level < len(module_ref) and module_ref[relative_level] == ".":
            relative_level += 1

        remainder = module_ref[relative_level:]
        if relative_level == 0:
            return remainder

        importer_dir = Path(importer_file).parent
        package_parts = [
            part for part in importer_dir.as_posix().split("/") if part and part != "."
        ]

        levels_up = max(relative_level - 1, 0)
        if levels_up > len(package_parts):
            return remainder

        base_parts = package_parts[: len(package_parts) - levels_up]
        if remainder:
            base_parts.extend([part for part in remainder.split(".") if part])

        return ".".join(base_parts)

    def _join_module_ref(self, module_ref: str, imported_name: str) -> str:
        module_ref = module_ref.strip()
        imported_name = imported_name.strip()
        if not module_ref:
            return imported_name
        return f"{module_ref}.{imported_name}"

    def _module_names_for_file(self, file_path: str) -> list[str]:
        if not file_path.endswith(".py"):
            return []

        if file_path.endswith("/__init__.py"):
            package_path = file_path[: -len("/__init__.py")]
            if not package_path:
                return []
            return [package_path.replace("/", ".")]

        if file_path == "__init__.py":
            return []

        module_path = file_path[:-3]
        return [module_path.replace("/", ".")]

    def _normalize_rel_path(self, file_path: str) -> str:
        path_obj = Path(file_path)
        try:
            resolved = path_obj.resolve()
            if resolved.is_absolute():
                try:
                    relative = resolved.relative_to(self.repo_root)
                    return relative.as_posix()
                except ValueError:
                    return resolved.as_posix()
        except Exception:
            pass

        normalized = str(path_obj).replace("\\", "/").lstrip("./")
        return normalized

    def _traverse_tree(self, node: Node):
        yield node
        for child in node.children:
            yield from self._traverse_tree(child)
