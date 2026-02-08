"""Unit tests for import symbol resolution."""

from pathlib import Path

from homllm.common.types import EntityInfo, FileInfo, SymbolInfo, SymbolKind
from homllm.indexer.graph_resolver import SymbolResolver
from homllm.indexer.interfaces import ParseResult
from homllm.indexer.parser import TreeSitterParser


def _parse_python(parser: TreeSitterParser, filename: str, code: str):
    ts_parser = parser.parsers["python"]
    tree = ts_parser.parse(code.encode("utf-8"))
    symbols = parser._extract_python_symbols(tree.root_node, code, filename)
    result = ParseResult(
        symbols=symbols,
        content=code,
        parse_error=False,
        tree=tree,
    )
    return result, symbols


def _import_entities_for_file(
    resolver: SymbolResolver,
    tree,
    content: str,
    file_path: str,
):
    specs = resolver.extract_import_specs(tree.root_node, content, file_path)
    entities = [
        EntityInfo(
            entity_id=f"imp:{idx}",
            entity_type="alias" if "." in spec.exposed_name and spec.import_kind == "import" else "import",
            name=spec.exposed_name,
            file_path=spec.file_path,
            span_start=spec.line_number,
            span_end=spec.line_number,
        )
        for idx, spec in enumerate(specs)
    ]
    return entities, specs


def test_symbol_resolver_resolves_from_import_to_function():
    resolver = SymbolResolver(repo_root=Path("."))
    parser = TreeSitterParser()

    importer_code = "from utils.payment import process_payment\n"
    imported_code = "def process_payment(amount):\n    return amount\n"

    importer_result, importer_symbols = _parse_python(parser, "main.py", importer_code)
    imported_result, imported_symbols = _parse_python(
        parser,
        "utils/payment.py",
        imported_code,
    )

    import_entities, import_specs = _import_entities_for_file(
        resolver,
        importer_result.tree,
        importer_code,
        "main.py",
    )

    files = [
        FileInfo(
            file_id="f1",
            path=Path("main.py"),
            language="python",
            content_hash="h1",
            line_count=1,
        ),
        FileInfo(
            file_id="f2",
            path=Path("utils/payment.py"),
            language="python",
            content_hash="h2",
            line_count=2,
        ),
    ]

    relations = resolver.resolve_import_entities(
        import_entities=import_entities,
        symbols=importer_symbols + imported_symbols,
        files=files,
        import_specs=import_specs,
    )

    assert len(relations) == 1
    relation = relations[0]
    assert relation.src_entity_id == import_entities[0].entity_id
    assert relation.relation_type == "resolves_to"
    assert relation.extraction_source == "symbol_resolution"
    assert relation.dst_entity_id == imported_symbols[0].id


def test_symbol_resolver_resolves_alias_to_function():
    resolver = SymbolResolver(repo_root=Path("."))
    parser = TreeSitterParser()

    importer_code = "from utils.payment import process_payment as pay\n"
    imported_code = "def process_payment(amount):\n    return amount\n"

    importer_result, importer_symbols = _parse_python(parser, "main.py", importer_code)
    _, imported_symbols = _parse_python(
        parser,
        "utils/payment.py",
        imported_code,
    )

    import_entities, import_specs = _import_entities_for_file(
        resolver,
        importer_result.tree,
        importer_code,
        "main.py",
    )
    import_entities[0] = EntityInfo(
        entity_id=import_entities[0].entity_id,
        entity_type="alias",
        name=import_entities[0].name,
        file_path=import_entities[0].file_path,
        span_start=import_entities[0].span_start,
        span_end=import_entities[0].span_end,
    )

    files = [
        FileInfo(
            file_id="f1",
            path=Path("main.py"),
            language="python",
            content_hash="h1",
            line_count=1,
        ),
        FileInfo(
            file_id="f2",
            path=Path("utils/payment.py"),
            language="python",
            content_hash="h2",
            line_count=2,
        ),
    ]

    relations = resolver.resolve_import_entities(
        import_entities=import_entities,
        symbols=importer_symbols + imported_symbols,
        files=files,
        import_specs=import_specs,
    )

    assert len(relations) == 1
    assert relations[0].dst_entity_id == imported_symbols[0].id


def test_symbol_resolver_resolves_relative_import():
    resolver = SymbolResolver(repo_root=Path("."))
    parser = TreeSitterParser()

    importer_code = "from .payment import process_payment\n"
    imported_code = "def process_payment():\n    return True\n"

    importer_result, importer_symbols = _parse_python(
        parser,
        "services/main.py",
        importer_code,
    )
    _, imported_symbols = _parse_python(
        parser,
        "services/payment.py",
        imported_code,
    )

    import_entities, import_specs = _import_entities_for_file(
        resolver,
        importer_result.tree,
        importer_code,
        "services/main.py",
    )

    files = [
        FileInfo(
            file_id="f1",
            path=Path("services/main.py"),
            language="python",
            content_hash="h1",
            line_count=1,
        ),
        FileInfo(
            file_id="f2",
            path=Path("services/payment.py"),
            language="python",
            content_hash="h2",
            line_count=2,
        ),
    ]

    relations = resolver.resolve_import_entities(
        import_entities=import_entities,
        symbols=importer_symbols + imported_symbols,
        files=files,
        import_specs=import_specs,
    )

    assert len(relations) == 1
    assert relations[0].dst_entity_id == imported_symbols[0].id


def test_symbol_resolver_returns_empty_when_definition_missing():
    resolver = SymbolResolver(repo_root=Path("."))
    parser = TreeSitterParser()

    importer_code = "from utils.payment import process_payment\n"
    importer_result, importer_symbols = _parse_python(parser, "main.py", importer_code)

    import_entities, import_specs = _import_entities_for_file(
        resolver,
        importer_result.tree,
        importer_code,
        "main.py",
    )

    files = [
        FileInfo(
            file_id="f1",
            path=Path("main.py"),
            language="python",
            content_hash="h1",
            line_count=1,
        )
    ]

    relations = resolver.resolve_import_entities(
        import_entities=import_entities,
        symbols=importer_symbols,
        files=files,
        import_specs=import_specs,
    )

    assert relations == []
