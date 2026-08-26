"""Prompt construction and action parsing for the bounded agent tool loop.

The loop speaks a strict one-JSON-object-per-turn contract over the existing
text provider seam (see docs/v4_architecture/12-agentic-loop-upgrade-plan.md).
Parsing reuses the tolerant extractors from the single-shot proposer so both
paths share the same recovery behavior for fenced JSON, prose-wrapped JSON,
and invalid escape sequences.
"""

from dataclasses import dataclass
import re

from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext
from homllm_v4.contracts.tool_loop import (
    AGENT_ACTION_NAMES,
    AgentToolLoopRequest,
    AgentToolObservation,
)
from homllm_v4.planning.provider_edit_proposer import (
    _extract_balanced_json_object,
    _extract_fenced_json,
    _repair_model_json,
)


@dataclass(frozen=True)
class ParsedAction:
    name: str
    arguments: dict[str, object]


def make_agent_tool_loop_request(
    *,
    task_id: str,
    query: str,
    intent: str,
    expected_behavior: str,
    verification_summary: str,
    evidence_context: tuple[EditProposalEvidenceContext, ...] = (),
    target_file: str | None = None,
    allowed_file_paths: tuple[str, ...] = (),
    repair_context: str = "",
    proposal_mode: str = "unified_diff",
    max_turns: int = 10,
) -> AgentToolLoopRequest:
    """Map planner-level fields onto the loop request contract."""
    return AgentToolLoopRequest(
        task_id=task_id,
        query=query,
        intent=intent,
        expected_behavior=expected_behavior,
        verification_summary=verification_summary,
        seed_evidence=evidence_context,
        seed_target_file=target_file,
        allowed_file_paths=allowed_file_paths,
        repair_context=repair_context,
        proposal_mode=proposal_mode,
        max_turns=max_turns,
    )


def build_initial_prompt(request: AgentToolLoopRequest) -> str:
    sections: list[str] = [
        "You are the HOM-LLM coding agent working inside a repository workspace.",
        "Goal: produce a bounded single-file patch that satisfies the verification command.",
        "",
        "Task:",
        f"Query: {request.query}",
        f"Intent: {request.intent}",
        f"Expected behavior: {request.expected_behavior}",
        f"Verification command: {request.verification_summary}",
        "",
        f"Turn budget: at most {max(1, int(request.max_turns))} actions in total. "
        "Every turn consumes one action, including malformed responses.",
        "Budget exploration accordingly: call propose_patch as soon as the evidence "
        "supports a fix. An imperfect patch is acceptable - it is verified and repaired "
        "automatically from test feedback. Running out of turns without proposing "
        "is the worst outcome.",
        "",
    ]
    if request.seed_evidence:
        sections.append("Seed evidence (retrieved for you; cite only these ids):")
        for item in request.seed_evidence:
            span = _format_span(item)
            content = item.content[:2000]
            sections.append(f"- [{item.evidence_id}] {item.file_path}{span}")
            sections.append(content)
    else:
        sections.append("Seed evidence: none supplied. Use read_file and search_repo to explore.")
    sections.extend(
        [
            "",
            "Tools (return exactly ONE JSON action object per turn, inside a ```json fence):",
            'read_file     {"action": "read_file", "file_path": "<path>", "start_line": <1-based int>, "end_line": <inclusive int>}',
            'search_repo   {"action": "search_repo", "query": "<text>"}',
            'propose_patch {"action": "propose_patch", "target_file": "<path>", "diff": "<unified diff>", "rationale": "<why>", "evidence_ids": ["<id>"]}',
            'finish        {"action": "finish", "rationale": "<why no safe fix exists>"}',
            "",
            "Rules:",
            "- Diff hunks must use line numbers that match the latest observed file content exactly.",
            "- Keep diffs minimal; do not touch unrelated lines.",
            "- Do not invent APIs or symbols; confirm names by reading real code before patching.",
            "- Only files in the allowed list may be patched.",
            "- Prefer propose_patch as soon as you are confident; do not explore without purpose.",
            "- Use finish only when no safe fix exists.",
        ]
    )
    if request.repair_context:
        sections.append(f"Repair context: {request.repair_context}")
    if request.allowed_file_paths:
        sections.append(f"Allowed files: {', '.join(request.allowed_file_paths)}")
    sections.append("NEXT_ACTION:")
    return "\n".join(sections)


_BUDGET_WARNING = (
    "BUDGET WARNING: only {remaining} action(s) remain after this turn. "
    "Call propose_patch NOW with your best hypothesis - an imperfect patch is "
    "verified and repaired from test feedback; an empty result is not."
)


def render_observation_block(
    turn_index: int,
    action_name: str,
    observation: AgentToolObservation,
    *,
    turns_total: int | None = None,
    turns_remaining: int | None = None,
) -> str:
    header = f"TURN {turn_index + 1}" + (
        f"/{turns_total}" if turns_total is not None else ""
    ) + f" ACTION {action_name}"
    if not observation.ok:
        header += f" ERROR {observation.error_code}"
    body = observation.content
    if turns_remaining is not None and 0 < turns_remaining <= 2:
        body = _BUDGET_WARNING.format(remaining=turns_remaining) + "\n" + body
    return f"{header}\nOBSERVATION:\n{body}"


def parse_agent_action(text: str) -> ParsedAction:
    stripped = text.strip()
    json_text = _extract_fenced_json(stripped)
    if json_text is None:
        json_text = _extract_balanced_json_object(stripped)
    import json

    try:
        payload = json.loads(_repair_model_json(json_text))
        if not isinstance(payload, dict):
            raise ValueError("agent action must be a JSON object")
        name = payload.get("action")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("agent action requires a string 'action' key")
        arguments = {key: value for key, value in payload.items() if key != "action"}
        return ParsedAction(name=name, arguments=arguments)
    except Exception as strict_error:
        lenient = _parse_agent_action_lenient(stripped)
        if lenient is not None:
            return lenient
        raise ValueError(f"agent action is not valid JSON: {strict_error}") from strict_error


_ACTION_NAME_VALUES = frozenset(AGENT_ACTION_NAMES)

_SHORT_FIELD_RES = {
    field: re.compile(r'"%s"\s*:\s*"([^"]*)"' % field)
    for field in ("target_file", "file_path", "query")
}
_RATIONALE_RE = re.compile(r'"rationale"\s*:\s*"(.*?)"(?=\s*[,}])', re.S)
_DIFF_START_RE = re.compile(r'"diff"\s*:\s*"')
# The diff value's closing quote followed by the next schema key; matching a
# known key keeps content quotes inside the diff (docstrings, kwargs) intact.
_DIFF_END_RE = re.compile(r'"\s*,\s*"(?:rationale|evidence_ids|risk_flags)"\s*:')


def _lenient_diff_value(text: str) -> str | None:
    match = _DIFF_START_RE.search(text)
    if match is None:
        return None
    start = match.end()
    end_match = _DIFF_END_RE.search(text, start)
    end = end_match.start() if end_match is not None else text.rfind('"')
    if end <= start:
        return None
    return text[start:end]


def _parse_agent_action_lenient(text: str) -> ParsedAction | None:
    """Schema-targeted fallback for actions no JSON repair can salvage.

    stealth/ox-alpha sometimes emits the diff with raw newlines AND unescaped
    inner quotes (Python docstrings), which makes string boundaries ambiguous
    for any generic repair. Field order follows the prompt schema, so each
    field is recovered by locating its key; anything structurally ambiguous
    returns None and the turn stays invalid.
    """
    action_match = re.search(r'"action"\s*:\s*"([^"]+)"', text)
    if action_match is None:
        return None
    name = action_match.group(1).strip()
    if name not in _ACTION_NAME_VALUES:
        return None
    arguments: dict[str, object] = {}
    for field, pattern in _SHORT_FIELD_RES.items():
        field_match = pattern.search(text)
        if field_match:
            arguments[field] = field_match.group(1)
    if name == "propose_patch":
        diff = _lenient_diff_value(text)
        target_file = arguments.get("target_file")
        if not diff or not isinstance(target_file, str) or not target_file:
            return None
        arguments["diff"] = diff
    rationale_match = _RATIONALE_RE.search(text)
    if rationale_match:
        arguments["rationale"] = rationale_match.group(1)
    ids_match = re.search(r'"evidence_ids"\s*:\s*\[(.*?)\]', text, re.S)
    if ids_match:
        arguments["evidence_ids"] = re.findall(r'"([^"]*)"', ids_match.group(1))
    for int_field in ("start_line", "end_line"):
        int_match = re.search(r'"%s"\s*:\s*(\d+)' % int_field, text)
        if int_match:
            arguments[int_field] = int(int_match.group(1))
    return ParsedAction(name=name, arguments=arguments)


def _format_span(item: EditProposalEvidenceContext) -> str:
    if item.span_start is None:
        return ""
    end = item.span_end if item.span_end is not None else "?"
    return f":{item.span_start}-{end}"
