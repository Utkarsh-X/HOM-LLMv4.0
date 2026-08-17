"""Tests for the ``swebench_gold`` canned-provider mode.

The fake edit provider must be able to apply a SWE-bench fixture's gold patch
deterministically, so the external suite is regression-runnable headlessly.
"""

import json
from types import SimpleNamespace

import pytest

from homllm_v4.evaluation.agent_benchmark import (
    _case_gold_patch,
    _case_provider_mode,
    _canned_provider_builder,
)
from homllm_v4.evaluation.canned_provider import (
    PromptAwareCannedProvider,
    canned_provider_content,
)

_GOLD_PATCH = """diff --git a/sympy/functions/elementary/complexes.py b/sympy/functions/elementary/complexes.py
--- a/sympy/functions/elementary/complexes.py
+++ b/sympy/functions/elementary/complexes.py
@@ -1,6 +1,8 @@
             arg2 = -S.ImaginaryUnit * arg
             if arg2.is_extended_nonnegative:
                 return arg2
+        if arg.is_extended_real:
+            return
         # reject result if all new conjugates are just wrappers around
         # an expression that was already in the arg
         conj = signsimp(arg.conjugate(), evaluate=False)
"""

_BUGGY_CONTENT = """            arg2 = -S.ImaginaryUnit * arg
            if arg2.is_extended_nonnegative:
                return arg2
        # reject result if all new conjugates are just wrappers around
        # an expression that was already in the arg
        conj = signsimp(arg.conjugate(), evaluate=False)
"""


def test_swebench_gold_requires_gold_patch() -> None:
    with pytest.raises(ValueError, match="swebench_gold_requires_gold_patch"):
        canned_provider_content(provider_mode="swebench_gold", target_content=_BUGGY_CONTENT)


def test_swebench_gold_applies_patch_to_content() -> None:
    new_content = canned_provider_content(
        provider_mode="swebench_gold",
        target_content=_BUGGY_CONTENT,
        gold_patch=_GOLD_PATCH,
    )
    assert "if arg.is_extended_real:" in new_content
    assert new_content.endswith("\n")  # trailing newline preserved


def test_swebench_gold_raises_on_context_mismatch() -> None:
    with pytest.raises(ValueError, match="hunk_context_mismatch"):
        canned_provider_content(
            provider_mode="swebench_gold",
            target_content="totally different content\n",
            gold_patch=_GOLD_PATCH,
        )


def test_prompt_aware_provider_uses_gold_patch() -> None:
    provider = PromptAwareCannedProvider(
        provider_mode="swebench_gold",
        target_file="sympy/functions/elementary/complexes.py",
        gold_patch=_GOLD_PATCH,
    )
    prompt = (
        "Evidence IDs: 1, 2\n"
        "Target file: sympy/functions/elementary/complexes.py\n"
        "Current content:\n"
        + _BUGGY_CONTENT
    )
    response = provider.propose_edit(SimpleNamespace(prompt=prompt))
    proposal = json.loads(response.text)
    assert proposal["target_file"] == "sympy/functions/elementary/complexes.py"
    assert "if arg.is_extended_real:" in proposal["new_content"]


def test_builder_threads_gold_patch_through() -> None:
    builder = _canned_provider_builder("swebench_gold", gold_patch=_GOLD_PATCH)
    provider = builder()
    assert provider.provider_mode == "swebench_gold"
    assert provider.gold_patch == _GOLD_PATCH
    # Non-gold modes stay unaffected.
    noop_builder = _canned_provider_builder("noop")
    assert noop_builder().gold_patch is None


class _Case:
    def __init__(self, metadata: dict) -> None:
        self.metadata = metadata


def test_case_helpers_read_provider_mode_and_gold_patch() -> None:
    case = _Case(
        {
            "provider_mode": "swebench_gold",
            "gold_patch": _GOLD_PATCH,
            "swebench_instance_id": "sympy__sympy-21627",
        }
    )
    assert _case_provider_mode(case) == "swebench_gold"  # type: ignore[arg-type]
    assert _case_gold_patch(case) == _GOLD_PATCH  # type: ignore[arg-type]
    assert _case_gold_patch(_Case({})) is None  # type: ignore[arg-type]
