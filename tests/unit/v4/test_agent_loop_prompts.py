import pytest

from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext
from homllm_v4.contracts.tool_loop import AgentToolObservation
from homllm_v4.planning.agent_loop_prompts import (
    build_initial_prompt,
    make_agent_tool_loop_request,
    parse_agent_action,
    render_observation_block,
)


def base_request(**overrides):
    defaults = dict(
        task_id="task-1",
        query="truncate_string edge case",
        intent="fix truncate_string",
        expected_behavior="truncate_string('abcdef', 2) == 'ab'",
        verification_summary="python -m pytest -q",
        seed_evidence=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="utils/string_tools.py",
                span_start=1,
                span_end=20,
                content="def truncate_string(text, max_length):\n    return text",
            ),
        ),
        seed_target_file="utils/string_tools.py",
        allowed_file_paths=("utils/string_tools.py",),
    )
    defaults.update(overrides)
    from homllm_v4.contracts.tool_loop import AgentToolLoopRequest

    return AgentToolLoopRequest(**defaults)


def test_prompt_contains_task_tools_and_seed() -> None:
    prompt = build_initial_prompt(base_request())

    for marker in (
        "truncate_string edge case",
        "fix truncate_string",
        "python -m pytest -q",
        "cand-1",
        "utils/string_tools.py",
        '"action": "read_file"',
        '"action": "search_repo"',
        '"action": "propose_patch"',
        '"action": "finish"',
        "NEXT_ACTION:",
    ):
        assert marker in prompt


def test_prompt_includes_repair_context_when_present() -> None:
    prompt = build_initial_prompt(base_request(repair_context="Previous attempt failed."))
    assert "Previous attempt failed." in prompt


def test_parse_agent_action_from_fenced_json_with_prose() -> None:
    text = 'Sure!\n```json\n{"action": "read_file", "file_path": "a.py"}\n```\nDone.'
    parsed = parse_agent_action(text)
    assert parsed.name == "read_file"
    assert parsed.arguments == {"file_path": "a.py"}


def test_parse_agent_action_repairs_invalid_escapes() -> None:
    text = r'{"action": "propose_patch", "target_file": "a.py", "diff": "\dagger"}'
    parsed = parse_agent_action(text)
    assert parsed.name == "propose_patch"
    assert parsed.arguments["diff"] == "\\dagger"


def test_parse_agent_action_repairs_raw_newlines_inside_diff_string() -> None:
    # stealth/ox-alpha emits multi-line diffs with literal newlines inside the
    # JSON string (observed live: 8 of 14 turns rejected for exactly this).
    diff = "--- a/a.py\n+++ b/a.py\n@@ -1,1 +1,2 @@\n-old\n+new"
    text = (
        '```json\n{\n  "action": "propose_patch",\n'
        '  "target_file": "a.py",\n  "diff": "' + diff + '",\n'
        '  "rationale": "fix",\n  "evidence_ids": []\n}\n```'
    )
    parsed = parse_agent_action(text)
    assert parsed.name == "propose_patch"
    assert parsed.arguments["diff"] == diff
    assert "\n" in str(parsed.arguments["diff"])


def test_parse_agent_action_lenient_recovers_unescaped_quotes_in_diff() -> None:
    # When the diff also contains unescaped inner quotes (docstrings), no
    # generic JSON repair can disambiguate string boundaries; the schema-
    # targeted fallback recovers the fields by key order instead.
    diff = (
        "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,6 @@\n"
        " def f():\n-    return 1\n+    \"\"\"docstring\"\"\"\n+    return 1"
    )
    text = (
        '```json\n{\n  "action": "propose_patch",\n'
        '  "target_file": "a.py",\n  "diff": "' + diff + '",\n'
        '  "rationale": "add docstring",\n'
        '  "evidence_ids": ["abc12345def"]\n}\n```'
    )
    parsed = parse_agent_action(text)
    assert parsed.name == "propose_patch"
    assert parsed.arguments["target_file"] == "a.py"
    assert parsed.arguments["diff"] == diff
    assert '"""docstring"""' in str(parsed.arguments["diff"])
    assert parsed.arguments["evidence_ids"] == ["abc12345def"]


def test_parse_agent_action_lenient_rejects_unsalvageable_actions() -> None:
    # Unknown action names are not fabricated into valid ones (malformed so
    # the strict path cannot accept them either)...
    with pytest.raises(ValueError):
        parse_agent_action('prose {"action": "deploy", "target_file": "a.py" trailing')
    with pytest.raises(ValueError):
        parse_agent_action("")
    # ...and propose_patch without a recoverable diff stays invalid (the
    # downstream loop validation still guards well-formed-but-diffless JSON).
    with pytest.raises(ValueError):
        parse_agent_action(
            '```json\n{"action": "propose_patch", "target_file": "a.py"\n```'
        )


def test_parse_agent_action_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_agent_action("no json here")
    with pytest.raises(ValueError):
        parse_agent_action('{"no_action": true}')
    with pytest.raises(ValueError):
        parse_agent_action("[1, 2, 3]")


def test_render_observation_block_ok_and_error() -> None:
    ok_block = render_observation_block(0, "read_file", AgentToolObservation(ok=True, content="hello"))
    assert "TURN 1" in ok_block
    assert "read_file" in ok_block
    assert "hello" in ok_block

    err_block = render_observation_block(
        2, "search_repo", AgentToolObservation(ok=False, content="", error_code="adapter_failed")
    )
    assert "TURN 3" in err_block
    assert "adapter_failed" in err_block


def test_make_request_maps_planner_fields() -> None:
    request = make_agent_tool_loop_request(
        task_id="task-1",
        query="q",
        intent="i",
        expected_behavior="e",
        verification_summary="v",
        evidence_context=(EditProposalEvidenceContext("c", "f.py", None, None, "x"),),
        target_file="f.py",
        repair_context="r",
        proposal_mode="unified_diff",
        max_turns=7,
    )
    assert request.max_turns == 7
    assert request.seed_target_file == "f.py"
    assert request.seed_evidence[0].evidence_id == "c"


def test_prompt_states_turn_budget() -> None:
    prompt = build_initial_prompt(base_request(max_turns=7))

    assert "Turn budget: at most 7 actions in total" in prompt
    assert "call propose_patch as soon as the evidence" in prompt


def test_render_observation_block_includes_turn_progress() -> None:
    block = render_observation_block(
        2,
        "read_file",
        AgentToolObservation(ok=True, content="hello"),
        turns_total=10,
        turns_remaining=7,
    )

    assert block.startswith("TURN 3/10 ACTION read_file")
    assert "BUDGET WARNING" not in block


def test_render_observation_block_warns_when_budget_running_out() -> None:
    warned = render_observation_block(
        8,
        "search_repo",
        AgentToolObservation(ok=True, content="body"),
        turns_total=10,
        turns_remaining=2,
    )
    assert "BUDGET WARNING: only 2 action(s) remain" in warned
    assert "body" in warned

    last_chance = render_observation_block(
        9,
        "read_file",
        AgentToolObservation(ok=True, content="body"),
        turns_total=10,
        turns_remaining=1,
    )
    assert "BUDGET WARNING: only 1 action(s) remain" in last_chance

    spent = render_observation_block(
        9,
        "read_file",
        AgentToolObservation(ok=True, content="body"),
        turns_total=10,
        turns_remaining=0,
    )
    assert "BUDGET WARNING" not in spent


def test_render_observation_block_without_totals_keeps_legacy_format() -> None:
    block = render_observation_block(0, "read_file", AgentToolObservation(ok=True, content="hello"))
    assert block.startswith("TURN 1 ACTION read_file")
