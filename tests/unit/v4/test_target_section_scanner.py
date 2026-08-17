from homllm_v4.planning.target_section_scanner import (
    significant_tokens,
    scan_target_sections,
    TargetSection,
)


def test_significant_tokens_filters_stopwords_and_short_words() -> None:
    tokens = significant_tokens("The quick brown fox and a dog are jumping")
    assert "the" not in tokens
    assert "and" not in tokens
    assert "are" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens
    assert "fox" in tokens
    assert "dog" in tokens
    assert "jumping" in tokens


def test_scan_target_sections_empty_content_or_tokens() -> None:
    assert scan_target_sections("", query="fix bug") == ()
    assert scan_target_sections("def foo(): pass", query="a an the") == ()


def test_scan_target_sections_finds_relevant_window() -> None:
    code = "\n".join(
        [
            "# Module docstring",
            "import os",
            "import sys",
            "",
            "def unrelated_helper():",
            "    return 42",
            "",
            "class ComplexHandler:",
            "    def eval_conjugate(self, arg):",
            "        # Fix recursion error in conjugate rewrite",
            "        if arg.is_zero:",
            "            return 0",
            "        return arg",
            "",
            "def another_function():",
            "    pass",
        ]
    )
    sections = scan_target_sections(
        code,
        query="RecursionError in conjugate rewrite when arg is zero",
        context="Fix the bug in conjugate rewrite",
        window_lines=10,
        step_lines=3,
        max_sections=2,
    )
    assert len(sections) >= 1
    top_section = sections[0]
    assert isinstance(top_section, TargetSection)
    assert "eval_conjugate" in top_section.content
    assert top_section.span_start >= 1
    assert top_section.span_end <= len(code.splitlines())
