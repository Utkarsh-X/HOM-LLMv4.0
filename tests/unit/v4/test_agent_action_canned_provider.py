"""Tests for ``AgentActionCannedProvider`` -- the bounded-loop companion to
:class:`PromptAwareCannedProvider`.

It must emit a one-turn ``{"action": "propose_patch", ...}`` payload the
agentic-loop parser accepts: the gold patch verbatim for ``swebench_gold``
mode, else a unified diff derived from the canned content transform against
the current content parsed from the prompt.
"""

import json
from types import SimpleNamespace

from homllm_v4.evaluation.canned_provider import AgentActionCannedProvider
from homllm_v4.planning.agent_loop_prompts import parse_agent_action
from homllm_v4.utils.unified_diff import apply_unified_diff

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

_BUGGY_CONTENT = """def parse_date(date_string, format_str):
        return datetime.strptime(date_string, format_str)
"""

_FIXED_CONTENT = _BUGGY_CONTENT.replace(
    "datetime.strptime(date_string, format_str)",
    "datetime.strptime(date_string.strip(), format_str)",
)


def _action_payload(provider: AgentActionCannedProvider, prompt: str) -> dict:
    response = provider.propose_edit(SimpleNamespace(prompt=prompt))
    return json.loads(response.text)


def test_agent_action_provider_emits_gold_patch_verbatim() -> None:
    provider = AgentActionCannedProvider(
        provider_mode="swebench_gold",
        target_file="sympy/functions/elementary/complexes.py",
        gold_patch=_GOLD_PATCH,
    )

    proposal = _action_payload(provider, prompt="no current content needed")

    assert proposal["action"] == "propose_patch"
    assert proposal["diff"] == _GOLD_PATCH
    assert proposal["rationale"] == "Deterministic canned agent action."


def test_agent_action_response_is_parseable_by_loop_and_credits_tokens() -> None:
    provider = AgentActionCannedProvider(
        provider_mode="swebench_gold", gold_patch=_GOLD_PATCH
    )

    response = provider.propose_edit(SimpleNamespace(prompt="prompt"))

    parsed = parse_agent_action(response.text)
    assert parsed.name == "propose_patch"
    assert parsed.arguments["diff"] == _GOLD_PATCH
    assert (response.tokens_in, response.tokens_out) == (1, 1)
    assert response.model == "canned-provider"
    assert response.metadata == {"provider": "canned-agent-actions"}


def test_agent_action_provider_converts_content_transform_to_unified_diff() -> None:
    provider = AgentActionCannedProvider(provider_mode="parse_date_strip")
    prompt = (
        "Evidence IDs: cand-1\n"
        "Target file: pkg/tasks/parsing.py\n"
        "Current content:\n" + _BUGGY_CONTENT
    )

    proposal = _action_payload(provider, prompt=prompt)

    diff = proposal["diff"]
    assert "--- a/pkg/tasks/parsing.py" in diff
    assert "+++ b/pkg/tasks/parsing.py" in diff
    assert "-        return datetime.strptime(date_string, format_str)" in diff
    assert "+        return datetime.strptime(date_string.strip(), format_str)" in diff

    # The emitted diff must round-trip through the harness applier.
    assert apply_unified_diff(_BUGGY_CONTENT, diff) == _FIXED_CONTENT


def test_agent_action_provider_defaults_target_file_when_prompt_omits_it() -> None:
    provider = AgentActionCannedProvider(provider_mode="parse_date_strip")

    proposal = _action_payload(
        provider, prompt="Current content:\n" + _BUGGY_CONTENT
    )

    assert "--- a/target.py" in proposal["diff"]
    assert "+++ b/target.py" in proposal["diff"]


def test_agent_action_provider_prompt_target_file_overrides_constructor_hint() -> None:
    provider = AgentActionCannedProvider(
        provider_mode="parse_date_strip", target_file="hint.py"
    )
    prompt = "Target file: real_target.py\nCurrent content:\n" + _BUGGY_CONTENT

    proposal = _action_payload(provider, prompt=prompt)

    assert "--- a/real_target.py" in proposal["diff"]
