from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Protocol

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import (
    PROPOSAL_MODE_FULL_CONTENT,
    PROPOSAL_MODE_UNIFIED_DIFF,
    EditProposalRequest,
    EditProposalResult,
    validate_proposal_mode,
)
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.bounded_edit_proposer import BoundedEditProposer
from homllm_v4.utils.unified_diff import apply_unified_diff

# Provider-output failures that a fresh provider call can plausibly fix.
_RETRYABLE_FAILURE_CODES = frozenset(
    {
        "provider_invocation_failed",
        "provider_diff_not_applicable",
    }
)


@dataclass(frozen=True)
class ProviderEditProposalRequest:
    task_id: str
    prompt: str
    response_format: str = "json"


@dataclass(frozen=True)
class ProviderEditProposalResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = "unknown"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _EvidenceContextRender:
    text: str
    item_count: int
    rendered_char_count: int
    truncated: bool


@dataclass(frozen=True)
class _PromptBuild:
    prompt: str
    prompt_char_count: int
    evidence_context_item_count: int
    evidence_context_rendered_char_count: int
    evidence_context_truncated: bool
    current_content_char_count: int
    current_content_truncated: bool


class EditProposalProvider(Protocol):
    def propose_edit(
        self,
        request: ProviderEditProposalRequest,
    ) -> ProviderEditProposalResponse:
        ...


class ProviderBackedEditProposer:
    def __init__(
        self,
        *,
        provider: EditProposalProvider,
        artifact_manager: ArtifactManager | None = None,
        max_evidence_item_chars: int = 2000,
        max_evidence_context_chars: int = 12000,
        max_prompt_chars: int | None = None,
    ) -> None:
        self.provider = provider
        self.artifact_manager = artifact_manager
        self.max_evidence_item_chars = max(1, int(max_evidence_item_chars))
        self.max_evidence_context_chars = max(1, int(max_evidence_context_chars))
        self.max_prompt_chars = None if max_prompt_chars is None else max(1, int(max_prompt_chars))
        self._attempt = 0

    def propose(self, request: EditProposalRequest) -> CapabilityResult[EditProposalResult]:
        validate_proposal_mode(request.proposal_mode)
        started = perf_counter()
        attempt_index = self._attempt
        self._attempt += 1
        provider_response: ProviderEditProposalResponse | None = None
        prompt_build = self._build_within_budget(request)
        prompt = prompt_build.prompt
        artifacts = self._write_prompt_artifact(request, prompt, attempt_index)
        if (
            self.max_prompt_chars is not None
            and prompt_build.prompt_char_count > self.max_prompt_chars
        ):
            return _failed(
                request=request,
                started=started,
                provider_response=None,
                prompt_build=prompt_build,
                code="provider_prompt_budget_exceeded",
                message="provider prompt exceeds configured maximum size",
                details={
                    "prompt_char_count": prompt_build.prompt_char_count,
                    "max_prompt_chars": self.max_prompt_chars,
                },
                artifacts=artifacts,
            )

        try:
            provider_response = self.provider.propose_edit(
                ProviderEditProposalRequest(
                    task_id=request.task_id,
                    prompt=prompt,
                )
            )
        except Exception as exc:
            return _failed(
                request=request,
                started=started,
                provider_response=None,
                prompt_build=prompt_build,
                code="provider_invocation_failed",
                message=str(exc),
                details=None,
                artifacts=artifacts,
            )

        artifacts += self._write_response_artifact(
            request,
            provider_response.text,
            attempt_index,
        )
        try:
            proposal = parse_provider_edit_response(
                provider_response.text,
                mode=request.proposal_mode,
            )
        except Exception as exc:
            finish_reason = str(
                getattr(provider_response, "metadata", {}).get("finish_reason", "")
            ).lower()
            if finish_reason in {"max_tokens", "length"}:
                code = "provider_response_truncated"
                details = {"finish_reason": finish_reason}
            else:
                code = "provider_response_invalid"
                details = None
            return _failed(
                request=request,
                started=started,
                provider_response=provider_response,
                prompt_build=prompt_build,
                code=code,
                message=str(exc),
                details=details,
                artifacts=artifacts,
            )

        unknown_evidence = tuple(sorted(set(proposal.evidence_ids) - set(request.evidence_ids)))
        if unknown_evidence:
            return _failed(
                request=request,
                started=started,
                provider_response=provider_response,
                prompt_build=prompt_build,
                code="proposal_evidence_scope_denied",
                message="proposal references evidence ids outside the request",
                details={"unknown_evidence_ids": unknown_evidence},
                artifacts=artifacts,
            )

        if proposal.diff is not None:
            try:
                applied = apply_unified_diff(request.current_content, proposal.diff)
            except ValueError as exc:
                return _failed(
                    request=request,
                    started=started,
                    provider_response=provider_response,
                    prompt_build=prompt_build,
                    code="provider_diff_not_applicable",
                    message=str(exc),
                    details={"proposal_mode": request.proposal_mode},
                    artifacts=artifacts,
                )
            proposal = replace(proposal, new_content=applied)

        bounded = BoundedEditProposer(proposer=lambda _: proposal).propose(request)
        return _with_provider_usage(
            bounded,
            started=started,
            provider_response=provider_response,
            prompt_build=prompt_build,
            request=request,
            artifacts=artifacts,
        )

    def _build_within_budget(self, request: EditProposalRequest) -> _PromptBuild:
        """Build the proposal prompt, shrinking the current-content section when needed.

        The current content is the full target file (up to the direct-read byte
        cap), which can exceed ``max_prompt_chars`` on real repositories. A
        hard failure there would kill the whole case, so when the budget is
        exceeded we first rebuild with a head+tail slice of the file and mark
        the truncation in telemetry. Only if the non-content part alone still
        overflows do we fail with ``provider_prompt_budget_exceeded``.
        """
        prompt_build = _build_edit_proposal_prompt_with_metadata(
            request,
            max_evidence_item_chars=self.max_evidence_item_chars,
            max_evidence_context_chars=self.max_evidence_context_chars,
        )
        if (
            self.max_prompt_chars is None
            or prompt_build.prompt_char_count <= self.max_prompt_chars
            or prompt_build.current_content_truncated
        ):
            return prompt_build
        non_content_chars = (
            prompt_build.prompt_char_count - prompt_build.current_content_char_count
        )
        content_cap = max(2000, self.max_prompt_chars - non_content_chars)
        return _build_edit_proposal_prompt_with_metadata(
            request,
            max_evidence_item_chars=self.max_evidence_item_chars,
            max_evidence_context_chars=self.max_evidence_context_chars,
            max_current_content_chars=content_cap,
        )

    def _write_prompt_artifact(
        self,
        request: EditProposalRequest,
        prompt: str,
        attempt_index: int,
    ) -> tuple[ArtifactRef, ...]:
        if self.artifact_manager is None:
            return ()
        segment = _safe_segment(request.task_id)
        refs = [
            self.artifact_manager.write_text(
                f"provider/{segment}/prompt.txt",
                prompt,
                "provider_prompt",
                "provider edit proposal prompt (latest attempt)",
            ),
            self.artifact_manager.write_text(
                f"provider/{segment}/attempt_{attempt_index}/prompt.txt",
                prompt,
                "provider_prompt",
                "provider edit proposal prompt (per-attempt history)",
            ),
        ]
        return tuple(refs)

    def _write_response_artifact(
        self,
        request: EditProposalRequest,
        response_text: str,
        attempt_index: int,
    ) -> tuple[ArtifactRef, ...]:
        if self.artifact_manager is None:
            return ()
        segment = _safe_segment(request.task_id)
        refs = [
            self.artifact_manager.write_text(
                f"provider/{segment}/response.txt",
                response_text,
                "provider_response",
                "provider edit proposal raw response (latest attempt)",
            ),
            self.artifact_manager.write_text(
                f"provider/{segment}/attempt_{attempt_index}/response.txt",
                response_text,
                "provider_response",
                "provider edit proposal raw response (per-attempt history)",
            ),
        ]
        return tuple(refs)


def build_edit_proposal_prompt(
    request: EditProposalRequest,
    *,
    max_evidence_item_chars: int = 2000,
    max_evidence_context_chars: int = 12000,
    max_current_content_chars: int | None = None,
) -> str:
    return _build_edit_proposal_prompt_with_metadata(
        request,
        max_evidence_item_chars=max_evidence_item_chars,
        max_evidence_context_chars=max_evidence_context_chars,
        max_current_content_chars=max_current_content_chars,
    ).prompt


def _build_edit_proposal_prompt_with_metadata(
    request: EditProposalRequest,
    *,
    max_evidence_item_chars: int,
    max_evidence_context_chars: int,
    max_current_content_chars: int | None = None,
) -> _PromptBuild:
    evidence_render = _render_evidence_context(
        request,
        max_evidence_item_chars=max_evidence_item_chars,
        max_evidence_context_chars=max_evidence_context_chars,
    )
    current_content, current_content_char_count, current_content_truncated = (
        _render_current_content(request.current_content, max_current_content_chars)
    )
    prompt = "\n".join(
        _prompt_instruction_lines(request)
        + (
            f"Task ID: {request.task_id}",
            f"Target file: {request.target_file}",
            f"Allowed files: {', '.join(request.allowed_file_paths)}",
            f"Intent: {request.intent}",
            f"Expected behavior: {request.expected_behavior}",
            *(("Repair context: " + request.repair_context,) if request.repair_context else ()),
            f"Evidence IDs: {', '.join(request.evidence_ids)}",
            f"Verification: {request.verification_summary}",
            evidence_render.text,
            "Current content:",
            current_content,
        )
    )
    return _PromptBuild(
        prompt=prompt,
        prompt_char_count=len(prompt),
        evidence_context_item_count=evidence_render.item_count,
        evidence_context_rendered_char_count=evidence_render.rendered_char_count,
        evidence_context_truncated=evidence_render.truncated,
        current_content_char_count=current_content_char_count,
        current_content_truncated=current_content_truncated,
    )


def _prompt_instruction_lines(request: EditProposalRequest) -> tuple[str, ...]:
    if request.proposal_mode == PROPOSAL_MODE_UNIFIED_DIFF:
        return (
            "You are proposing a bounded single-file edit.",
            "Return a JSON object with keys: target_file, rationale, evidence_ids, risk_flags inside a ```json fence.",
            "Then return the unified diff inside a separate ```diff fence, with NO JSON escaping of the diff.",
            "diff must be a unified diff against the Current content section below.",
            "Include '--- a/<target_file>' and '+++ b/<target_file>' header lines.",
            "Hunks use '@@ -old_start,old_count +new_start,new_count @@' with line numbers that match the Current content exactly.",
            "Context lines start with a single space; additions start with '+'; deletions start with '-'.",
            "Make the smallest set of hunks that fixes the bug; do not touch unrelated lines.",
            "If you cannot express the fix as a diff, you may instead return the complete file as new_content inside the JSON object.",
            "For no-op or validation-only tasks, return current content unchanged as new_content.",
            "Exact examples in Expected behavior are mandatory acceptance criteria.",
            "The proposed change must satisfy the Verification command.",
            "Do not use a plausible generic fix if it violates an exact expected output.",
            "Do not call a helper that re-acquires a non-reentrant lock while inside that lock.",
            "Do not modify files outside the allowed file list.",
            "Do not cite evidence ids that are not listed in this request.",
        )
    return (
        "You are proposing a bounded single-file edit.",
        "Return only JSON with keys: target_file, new_content, rationale, evidence_ids, risk_flags.",
        "new_content must be the complete replacement content for the entire target file.",
        "new_content must be a valid JSON string with escaped newlines and quotes.",
        "After JSON parsing, new_content must be normal source text with normal quotes.",
        "Do not include literal backslash-escaped quote characters in source code unless they already exist.",
        "Do not return a snippet, diff, patch, or partial function body.",
        "Do not use Python triple-quoted strings for new_content.",
        "For no-op or validation-only tasks, return current content unchanged.",
        "Exact examples in Expected behavior are mandatory acceptance criteria.",
        "The proposed new_content must satisfy the Verification command.",
        "Do not use a plausible generic fix if it violates an exact expected output.",
        "Do not call a helper that re-acquires a non-reentrant lock while inside that lock.",
        "Do not modify files outside the allowed file list.",
        "Do not cite evidence ids that are not listed in this request.",
    )


def _render_current_content(
    content: str,
    max_chars: int | None,
) -> tuple[str, int, bool]:
    """Render current content, slicing head+tail when it exceeds ``max_chars``.

    Returns ``(rendered, original_char_count, truncated)``. Truncation keeps
    whole lines from the head and tail of the file with an explicit omission
    marker, so the model still sees imports and the end of the file (where the
    edited functions usually live) without silently dropping context.
    """
    if max_chars is None or len(content) <= max_chars:
        return content, len(content), False
    if "\n" not in content:
        return content[: max(1, int(max_chars))], len(content), True
    lines = content.splitlines(keepends=True)
    marker_reserve = 64
    max_chars = max(1, int(max_chars))
    head_budget = max(1, (max_chars - marker_reserve) // 2)
    head_lines, head_used = _take_whole_lines(lines, head_budget)
    tail_budget = max(0, max_chars - marker_reserve - head_used)
    tail_lines, _ = _take_whole_lines(reversed(lines), tail_budget)
    tail_lines.reverse()
    skipped = len(lines) - len(head_lines) - len(tail_lines)
    marker = f"\n[--- {skipped} lines omitted ---]\n"
    truncated = "".join(head_lines) + marker + "".join(tail_lines)
    return truncated, len(content), True


def _take_whole_lines(
    lines,
    budget: int,
) -> tuple[list[str], int]:
    taken: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) > budget:
            break
        taken.append(line)
        used += len(line)
    return taken, used


def _render_evidence_context(
    request: EditProposalRequest,
    *,
    max_evidence_item_chars: int,
    max_evidence_context_chars: int,
) -> _EvidenceContextRender:
    if not request.evidence_context:
        return _EvidenceContextRender(
            text="Evidence context: none supplied",
            item_count=0,
            rendered_char_count=0,
            truncated=False,
        )
    item_limit = max(1, int(max_evidence_item_chars))
    remaining = max(1, int(max_evidence_context_chars))
    lines = ["Evidence context:"]
    rendered_char_count = 0
    truncated = False
    last_index = len(request.evidence_context) - 1
    for index, item in enumerate(request.evidence_context):
        if remaining <= 0:
            lines.append("[evidence context budget exhausted]")
            truncated = True
            break
        content = item.content[: min(item_limit, remaining)]
        was_truncated = len(content) < len(item.content)
        truncated = truncated or was_truncated
        lines.append(
            f"[{item.evidence_id}] "
            f"{_format_location(item.file_path, item.span_start, item.span_end)}"
        )
        lines.append(content)
        rendered_char_count += len(content)
        if was_truncated:
            lines.append("[truncated]")
        remaining -= len(content)
        if remaining <= 0 and index != last_index:
            lines.append("[evidence context budget exhausted]")
            truncated = True
            break
    return _EvidenceContextRender(
        text="\n".join(lines),
        item_count=len(request.evidence_context),
        rendered_char_count=rendered_char_count,
        truncated=truncated,
    )


def _format_location(file_path: str, span_start: int | None, span_end: int | None) -> str:
    if span_start is None and span_end is None:
        return file_path
    if span_start is not None and span_end is not None:
        return f"{file_path}:{span_start}-{span_end}"
    if span_start is not None:
        return f"{file_path}:{span_start}"
    return f"{file_path}:?-{span_end}"


def parse_provider_edit_response(
    text: str,
    *,
    mode: str = PROPOSAL_MODE_FULL_CONTENT,
) -> EditProposalResult:
    validate_proposal_mode(mode)
    raw_text = _json_text_from_provider_response(text)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as first_error:
        repaired = _repair_model_json(raw_text)
        if repaired == raw_text:
            raise first_error
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as repair_error:
            raise ValueError(
                f"provider response JSON invalid after repair: {repair_error}"
            ) from first_error
    if not isinstance(data, dict):
        raise ValueError("provider response must be a JSON object")

    required = ("target_file", "rationale", "evidence_ids", "risk_flags")
    if mode == PROPOSAL_MODE_FULL_CONTENT:
        required = ("target_file", "new_content", "rationale", "evidence_ids", "risk_flags")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"provider response missing keys: {', '.join(missing)}")

    if not isinstance(data["evidence_ids"], list):
        raise ValueError("provider response evidence_ids must be a list")
    if not isinstance(data["risk_flags"], list):
        raise ValueError("provider response risk_flags must be a list")

    diff: str | None = None
    if mode == PROPOSAL_MODE_UNIFIED_DIFF:
        fenced_diff = _extract_fenced_diff(text)
        if fenced_diff is not None:
            new_content = ""
            diff = fenced_diff
        elif "new_content" in data:
            new_content = _string_field(data, "new_content")
        elif "diff" in data:
            new_content = ""
            diff = _string_field(data, "diff")
        else:
            raise ValueError("provider response missing keys: diff")
    else:
        new_content = _string_field(data, "new_content")

    return EditProposalResult(
        target_file=_string_field(data, "target_file"),
        new_content=new_content,
        rationale=_string_field(data, "rationale"),
        evidence_ids=tuple(str(item) for item in data["evidence_ids"]),
        risk_flags=tuple(str(item) for item in data["risk_flags"]),
        diff=diff,
    )


def _json_text_from_provider_response(text: str) -> str:
    stripped = text.strip()
    fenced = _extract_fenced_json(stripped)
    if fenced is not None:
        return fenced
    return _extract_balanced_json_object(stripped)


def _extract_fenced_diff(text: str) -> str | None:
    """Return the first `````diff``/`````patch`` fence, or None when absent.

    Diff fences carry the raw unified diff so the model does not have to
    JSON-escape code (which small models do unreliably). The JSON metadata
    object is parsed separately from the rest of the response.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate.startswith("```"):
            continue
        language = candidate[3:].strip().lower()
        if language not in ("diff", "patch"):
            continue
        for close_index in range(index + 1, len(lines)):
            if lines[close_index].strip() == "```":
                return "\n".join(lines[index + 1 : close_index]).strip()
    return None


def _extract_fenced_json(text: str) -> str | None:
    """Return the first `````json`` fenced block, or None when absent.

    Unlike the previous implementation this accepts fences anywhere in the
    response (small models frequently wrap JSON with explanatory prose) and
    tolerates a missing closing fence by falling back to brace extraction.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate.startswith("```"):
            continue
        language = candidate[3:].strip().lower()
        if language and not language.startswith("json"):
            continue
        for close_index in range(index + 1, len(lines)):
            if lines[close_index].strip() == "```":
                return "\n".join(lines[index + 1 : close_index]).strip()
    return None


def _extract_balanced_json_object(text: str) -> str:
    """Extract the outermost balanced JSON object from arbitrary prose.

    Scans from the first ``{`` and tracks nesting while respecting string
    literals and escape sequences, returning the span that closes at depth 0.
    Returns the input unchanged when no balanced object is found so the
    caller's ``json.loads`` produces the underlying error.
    """
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text


_VALID_JSON_ESCAPE_NEXT = frozenset('"\\/bfnrtu')


def _repair_invalid_json_escapes(text: str) -> str:
    r"""Repair model output where a backslash precedes a non-JSON escape char.

    Providers occasionally emit source code containing a literal backslash
    (e.g. ``r'%s^{\dagger}'``) without doubling it inside the JSON string,
    producing ``Invalid \\escape`` errors. This repairs such escapes by
    doubling the backslash only when the following character is not a valid
    JSON escape, leaving valid escapes untouched. Returns the input unchanged
    when no repair was needed.
    """
    if "\\" not in text:
        return text
    out: list[str] = []
    changed = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char != "\\" or index + 1 >= length:
            out.append(char)
            index += 1
            continue
        following = text[index + 1]
        if following in _VALID_JSON_ESCAPE_NEXT:
            out.append(char)
            out.append(following)
        else:
            out.append("\\\\")
            out.append(following)
            changed = True
        index += 2
    return "".join(out) if changed else text


_CONTROL_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _repair_unescaped_control_chars(text: str) -> str:
    r"""Repair model output where raw control characters sit inside JSON strings.

    stealth/ox-alpha emits multi-line diffs with literal newlines inside the
    ``diff`` string instead of ``\n`` escapes, so strict ``json.loads``
    rejects otherwise well-formed actions ("Invalid control character").
    This rewrites raw control characters (< 0x20) inside string literals to
    their JSON escapes; control characters outside strings are structural
    whitespace (pretty-printing) and are left untouched. Returns the input
    unchanged when no repair was needed.
    """
    out: list[str] = []
    changed = False
    in_string = False
    escaped = False
    for char in text:
        code = ord(char)
        if not in_string:
            if char == '"':
                in_string = True
            out.append(char)
            continue
        if escaped:
            escaped = False
            if code < 0x20:
                # A lone backslash directly before a control char cannot be
                # legal JSON; double the backslash so the emitted escape pair
                # parses (the value keeps backslash + control character).
                out.append("\\")
                out.append(_CONTROL_ESCAPES.get(char, f"\\u{code:04x}"))
                changed = True
            else:
                out.append(char)
            continue
        if char == "\\":
            escaped = True
            out.append(char)
            continue
        if char == '"':
            in_string = False
            out.append(char)
            continue
        if code < 0x20:
            out.append(_CONTROL_ESCAPES.get(char, f"\\u{code:04x}"))
            changed = True
            continue
        out.append(char)
    return "".join(out) if changed else text


def _repair_model_json(text: str) -> str:
    """Apply all known JSON repairs in one pass for second-chance parses."""
    return _repair_unescaped_control_chars(_repair_invalid_json_escapes(text))


def _string_field(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"provider response {key} must be a string")
    return value


def _failed(
    *,
    request: EditProposalRequest,
    started: float,
    provider_response: ProviderEditProposalResponse | None,
    prompt_build: _PromptBuild,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    artifacts: tuple[ArtifactRef, ...] = (),
) -> CapabilityResult[EditProposalResult]:
    return CapabilityResult(
        capability_name="edit.propose.provider",
        ok=False,
        output=None,
        error=CapabilityError(
            code=code,
            message=message,
            recoverable=True,
            retryable=code in _RETRYABLE_FAILURE_CODES,
            details={"target_file": request.target_file, **(details or {})},
        ),
        telemetry=_telemetry(
            request=request,
            started=started,
            provider_response=provider_response,
            prompt_build=prompt_build,
            output_summary={"code": code},
        ),
        artifacts=artifacts,
    )


def _with_provider_usage(
    result: CapabilityResult[EditProposalResult],
    *,
    started: float,
    provider_response: ProviderEditProposalResponse,
    prompt_build: _PromptBuild,
    request: EditProposalRequest,
    artifacts: tuple[ArtifactRef, ...],
) -> CapabilityResult[EditProposalResult]:
    return CapabilityResult(
        capability_name="edit.propose.provider",
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=_telemetry(
            request=request,
            started=started,
            provider_response=provider_response,
            prompt_build=prompt_build,
            output_summary=result.telemetry.output_summary,
        ),
        artifacts=result.artifacts + artifacts,
    )


def _safe_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "task"


def _telemetry(
    *,
    request: EditProposalRequest,
    started: float,
    provider_response: ProviderEditProposalResponse | None,
    prompt_build: _PromptBuild,
    output_summary: dict[str, object],
) -> CapabilityTelemetry:
    token_usage: dict[str, int] = {}
    model_usage: dict[str, object] = {}
    if provider_response is not None:
        token_usage = {
            "input": provider_response.tokens_in,
            "output": provider_response.tokens_out,
        }
        model_usage = {"model": provider_response.model, **provider_response.metadata}

    enriched_output_summary = {
        **output_summary,
        "prompt_char_count": prompt_build.prompt_char_count,
        "evidence_context_item_count": prompt_build.evidence_context_item_count,
        "evidence_context_rendered_char_count": prompt_build.evidence_context_rendered_char_count,
        "evidence_context_truncated": prompt_build.evidence_context_truncated,
        "current_content_char_count": prompt_build.current_content_char_count,
        "current_content_truncated": prompt_build.current_content_truncated,
    }

    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=int((perf_counter() - started) * 1000),
        input_summary={
            "task_id": request.task_id,
            "target_file": request.target_file,
            "evidence_count": len(request.evidence_ids),
        },
        output_summary=enriched_output_summary,
        token_usage=token_usage,
        model_usage=model_usage,
        degraded=False,
        degradation_reason=None,
    )
