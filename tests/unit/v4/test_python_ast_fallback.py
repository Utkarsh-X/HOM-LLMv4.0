from homllm.indexer.parser import _PythonAstParser


def test_python_ast_fallback_links_parent_nodes_for_indexing_consumers() -> None:
    tree = _PythonAstParser().parse(
        b"VALUE = 1\n\n\ndef load():\n    return VALUE\n"
    )

    module = tree.root_node
    assert module.children

    for child in module.children:
        assert child.parent is module

    function = next(child for child in module.children if child.type == "function_definition")
    body = function.child_by_field_name("body")
    assert body is not None
    assert function.parent is module
    assert body.parent is function
