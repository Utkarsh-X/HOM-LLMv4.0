"""Unit tests for AST-based call graph extraction."""

from homllm.indexer.graph_builder import GraphBuilder
from homllm.indexer.interfaces import ParseResult
from homllm.indexer.parser import TreeSitterParser


def _parse_and_build_edges(filename: str, code: str):
    parser = TreeSitterParser()
    ts_parser = parser.parsers["python"]
    tree = ts_parser.parse(code.encode("utf-8"))
    symbols = parser._extract_python_symbols(tree.root_node, code, filename)

    result = ParseResult(
        symbols=symbols,
        content=code,
        parse_error=False,
        tree=tree,
    )

    builder = GraphBuilder(entity_centric_enabled=False)
    builder.add_file_result(filename, result)

    return result, builder.build_call_graph()


def test_ast_call_graph_ignores_comment_calls():
    code = (
        "def caller():\n"
        "    # callee()\n"
        "    pass\n\n"
        "def callee():\n"
        "    pass\n"
    )

    _, edges = _parse_and_build_edges("comment_calls.py", code)
    assert edges == []


def test_ast_call_graph_ignores_string_literals():
    code = (
        "def caller():\n"
        "    print('calling callee()')\n"
        "    callee()\n\n"
        "def callee():\n"
        "    pass\n"
    )

    result, edges = _parse_and_build_edges("string_calls.py", code)
    symbols_by_id = {symbol.id: symbol for symbol in result.symbols}

    resolved = [
        (
            symbols_by_id[edge.caller_id].name,
            symbols_by_id[edge.callee_id].name,
        )
        for edge in edges
    ]
    assert resolved == [("caller", "callee")]


def test_ast_call_graph_method_resolution_uses_receiver_type():
    code = (
        "class User:\n"
        "    def save(self):\n"
        "        pass\n\n"
        "class File:\n"
        "    def save(self):\n"
        "        pass\n\n"
        "def process():\n"
        "    user = User()\n"
        "    user.save()\n"
    )

    result, edges = _parse_and_build_edges("method_resolution.py", code)
    symbols_by_id = {symbol.id: symbol for symbol in result.symbols}

    save_edges = [
        edge
        for edge in edges
        if symbols_by_id[edge.callee_id].name == "save"
    ]
    assert len(save_edges) == 1

    save_edge = save_edges[0]
    caller = symbols_by_id[save_edge.caller_id]
    callee = symbols_by_id[save_edge.callee_id]

    assert caller.name == "process"
    assert callee.parent_id is not None

    parent = symbols_by_id[callee.parent_id]
    assert parent.name == "User"


def test_ast_call_graph_handles_nested_calls():
    code = (
        "def outer():\n"
        "    def inner():\n"
        "        helper()\n"
        "    inner()\n\n"
        "def helper():\n"
        "    pass\n"
    )

    result, edges = _parse_and_build_edges("nested_calls.py", code)
    symbols_by_id = {symbol.id: symbol for symbol in result.symbols}

    resolved = {
        (
            symbols_by_id[edge.caller_id].name,
            symbols_by_id[edge.callee_id].name,
        )
        for edge in edges
    }

    assert ("inner", "helper") in resolved
    assert ("outer", "inner") in resolved
