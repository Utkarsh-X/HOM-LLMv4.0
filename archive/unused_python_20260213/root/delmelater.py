# delmelater.py
from tree_sitter import Parser

from tree_sitter_language_pack import get_language

parser = Parser()
parser.language = get_language("python")

print("TREE-SITTER PARSER READY")