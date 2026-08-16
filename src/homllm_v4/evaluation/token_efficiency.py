"""Token-efficiency comparison for the headless agent loop.

Measures how much context the evidence-first pipeline actually feeds the edit
provider versus a naive baseline that dumps the whole target file (or the
whole repository) into the prompt.

Design:
- Each internal benchmark case runs through the real `homllm-agent` pipeline
  with the deterministic canned provider (fake mode, no API key), so the
  planner metrics (`prompt_char_count`, `evidence_context_*`) reflect the
  actual retrieval -> evidence -> prompt assembly path.
- The naive baselines are computed deterministically from the case workspace:
  full target file content and full repository text (all source files).
- The ratio `naive_full_repo_chars / v4_prompt_chars` is the headline
  efficiency number: how many characters of naive context the pipeline
  avoided feeding the model.

This is a regression/safety harness (no live provider tokens are spent).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.evaluation.agent_benchmark import (
    INTERNAL_AGENT_BENCHMARK_CASES,
    AgentBenchmarkCase,
    _case_provider_mode,
    _canned_provider_builder,
)
from homllm_v4.runtime.agent_run import HomllmAgentRunRequest
from homllm_v4.runtime.agent_run import run_homllm_agent
from homllm_v4.serialization.json import to_jsonable


@dataclass(frozen=True)
class TokenEfficiencyCaseResult:
    case_id: str
    target_file: str | None
    v4_prompt_chars: int
    v4_evidence_item_count: int
    v4_evidence_rendered_chars: int
    v4_evidence_truncated: bool
    naive_full_file_chars: int
    naive_full_repo_chars: int
    ratio_full_file: float
    ratio_full_repo: float


@dataclass(frozen=True)
class TokenEfficiencyRunResult:
    run_id: str
    total_cases: int
    case_results: tuple[TokenEfficiencyCaseResult, ...]
    summary_metrics: dict[str, object]


def run_token_efficiency_comparison(
    *,
    config_path: Path,
    source_workspace_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    run_id: str | None = None,
    case_ids: tuple[str, ...] | None = None,
    max_prompt_chars: int | None = None,
    provider_repair_attempts: int = 0,
    index_skip_vectors: bool = True,
    agent_runner=run_homllm_agent,
) -> TokenEfficiencyRunResult:
    config_path = Path(config_path)
    if not config_path.exists():
        raise ValueError(f"config_not_found: {config_path}")
    source_workspace_root = Path(source_workspace_root).resolve()
    if not source_workspace_root.exists():
        raise ValueError(f"source_workspace_root_not_found: {source_workspace_root}")

    resolved_run_id = run_id or str(uuid4())
    workspace_root = Path(workspace_root).resolve()
    artifact_root = Path(artifact_root).resolve()
    cases = _select_cases(case_ids)
    artifact_manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )
    artifact_manager.create_run(
        resolved_run_id,
        {
            "entrypoint": "homllm_v4.evaluation.token_efficiency.run_token_efficiency_comparison",
            "case_count": len(cases),
            "provider_mode": "fake",
        },
    )

    case_results = tuple(
        _run_case(
            case=case,
            benchmark_run_id=resolved_run_id,
            config_path=config_path,
            source_workspace_root=source_workspace_root,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            max_prompt_chars=max_prompt_chars,
            provider_repair_attempts=provider_repair_attempts,
            index_skip_vectors=index_skip_vectors,
            agent_runner=agent_runner,
        )
        for case in cases
    )
    result = TokenEfficiencyRunResult(
        run_id=resolved_run_id,
        total_cases=len(case_results),
        case_results=case_results,
        summary_metrics=_summary_metrics(case_results),
    )
    artifact_manager.write_json(
        "evaluation/token_efficiency_summary.json",
        result,
        "evaluation",
        "token efficiency comparison summary",
    )
    dump_run_result(
        Path(artifact_root) / resolved_run_id / "token_efficiency.json",
        result,
    )
    return result


def _run_case(
    *,
    case: AgentBenchmarkCase,
    benchmark_run_id: str,
    config_path: Path,
    source_workspace_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    max_prompt_chars: int | None,
    provider_repair_attempts: int,
    index_skip_vectors: bool,
    agent_runner,
) -> TokenEfficiencyCaseResult:
    case_workspace = _copy_case_workspace(
        source_workspace_root=source_workspace_root,
        workspace_root=workspace_root,
        benchmark_run_id=benchmark_run_id,
        case_id=case.case_id,
    )
    case_run_id = f"{benchmark_run_id}-{case.case_id}"
    provider_mode = _case_provider_mode(case)
    result = agent_runner(
        HomllmAgentRunRequest(
            config_path=config_path,
            workspace_root=case_workspace,
            artifact_root=artifact_root,
            run_id=case_run_id,
            query=case.query,
            smoke_safe=True,
            answer_provider_mode="summary",
            edit_intent=case.edit_intent,
            expected_behavior=case.expected_behavior,
            target_file=case.target_file,
            verification_argv=case.verification_argv,
            live_provider_name="gemini",
            live_model="canned",
            live_api_key=None,
            live_max_output_tokens=1024,
            max_prompt_chars=max_prompt_chars,
            provider_repair_attempts=provider_repair_attempts,
            prepare_index=case.prepare_index,
            index_skip_vectors=index_skip_vectors,
            edit_provider_builder=_canned_provider_builder(provider_mode),
            edit_require_live_api_key=False,
        )
    )

    planner_metrics = _read_planner_metrics(Path(result.trajectory_path))
    v4_prompt_chars = int(planner_metrics.get("prompt_char_count", 0))
    v4_evidence_item_count = int(
        planner_metrics.get("evidence_context_item_count", 0)
    )
    v4_evidence_rendered_chars = int(
        planner_metrics.get("evidence_context_rendered_char_count", 0)
    )
    v4_evidence_truncated = bool(
        planner_metrics.get("evidence_context_truncated", False)
    )

    resolved_target = planner_metrics.get("resolved_target_file")
    naive_full_file_chars = 0
    if isinstance(resolved_target, str) and resolved_target:
        target_path = case_workspace / resolved_target
        if target_path.is_file():
            naive_full_file_chars = len(
                target_path.read_text(encoding="utf-8", errors="replace")
            )
    naive_full_repo_chars = _repo_text_chars(case_workspace)

    ratio_full_file = _ratio(naive_full_file_chars, v4_prompt_chars)
    ratio_full_repo = _ratio(naive_full_repo_chars, v4_prompt_chars)
    return TokenEfficiencyCaseResult(
        case_id=case.case_id,
        target_file=str(resolved_target) if isinstance(resolved_target, str) else None,
        v4_prompt_chars=v4_prompt_chars,
        v4_evidence_item_count=v4_evidence_item_count,
        v4_evidence_rendered_chars=v4_evidence_rendered_chars,
        v4_evidence_truncated=v4_evidence_truncated,
        naive_full_file_chars=naive_full_file_chars,
        naive_full_repo_chars=naive_full_repo_chars,
        ratio_full_file=ratio_full_file,
        ratio_full_repo=ratio_full_repo,
    )


def _read_planner_metrics(trajectory_path: Path) -> dict[str, object]:
    try:
        data = json.loads(trajectory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    planner = metrics.get("planner")
    if not isinstance(planner, dict):
        return {}
    return dict(planner)


def _summary_metrics(
    case_results: tuple[TokenEfficiencyCaseResult, ...],
) -> dict[str, object]:
    if not case_results:
        return {
            "case_count": 0,
            "avg_ratio_full_repo": 0.0,
            "avg_v4_prompt_chars": 0.0,
            "avg_naive_full_repo_chars": 0.0,
        }
    avg_ratio_full_repo = (
        sum(case.ratio_full_repo for case in case_results) / len(case_results)
    )
    avg_ratio_full_file = (
        sum(case.ratio_full_file for case in case_results) / len(case_results)
    )
    avg_v4_prompt_chars = (
        sum(case.v4_prompt_chars for case in case_results) / len(case_results)
    )
    avg_naive_full_repo_chars = (
        sum(case.naive_full_repo_chars for case in case_results) / len(case_results)
    )
    avg_naive_full_file_chars = (
        sum(case.naive_full_file_chars for case in case_results) / len(case_results)
    )
    return {
        "case_count": len(case_results),
        "avg_ratio_full_repo": avg_ratio_full_repo,
        "avg_ratio_full_file": avg_ratio_full_file,
        "avg_v4_prompt_chars": avg_v4_prompt_chars,
        "avg_naive_full_repo_chars": avg_naive_full_repo_chars,
        "avg_naive_full_file_chars": avg_naive_full_file_chars,
    }


def _select_cases(case_ids: tuple[str, ...] | None) -> tuple[AgentBenchmarkCase, ...]:
    if case_ids is None:
        return INTERNAL_AGENT_BENCHMARK_CASES
    by_id = {case.case_id: case for case in INTERNAL_AGENT_BENCHMARK_CASES}
    missing = tuple(case_id for case_id in case_ids if case_id not in by_id)
    if missing:
        raise ValueError(f"unknown_agent_benchmark_case: {missing[0]}")
    return tuple(by_id[case_id] for case_id in case_ids)


def _copy_case_workspace(
    *,
    source_workspace_root: Path,
    workspace_root: Path,
    benchmark_run_id: str,
    case_id: str,
) -> Path:
    target = workspace_root / benchmark_run_id / "cases" / case_id
    if target.exists():
        raise ValueError(f"case_workspace_exists: {target}")
    shutil.copytree(
        source_workspace_root,
        target,
        ignore=_ignore_workspace_copy_artifacts,
    )
    return target


def _ignore_workspace_copy_artifacts(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _repo_text_chars(workspace_root: Path) -> int:
    total = 0
    for path in workspace_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace_root).as_posix()
        if _ignored_repo_path(relative):
            continue
        try:
            total += len(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return total


def _ignored_repo_path(relative_path: str) -> bool:
    parts = set(Path(relative_path).parts)
    if parts & {".git", ".homllm", "__pycache__", ".pytest_cache"}:
        return True
    return relative_path.endswith((".pyc", ".pyo"))


def _ratio(naive_chars: int, v4_chars: int) -> float:
    if v4_chars <= 0:
        return 0.0
    return naive_chars / v4_chars


def dump_run_result(path: Path, result: TokenEfficiencyRunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_jsonable(result), indent=2, sort_keys=True) + "\n"
    temp_path = path.with_name(".tmp-token-efficiency.json")
    temp_path.write_text(text, encoding="utf-8", newline="")
    temp_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Standalone entrypoint for the token-efficiency comparison.

    Usage:
        python -m homllm_v4.evaluation.token_efficiency \
            --config <yaml> --source-workspace-root <repo> \
            --workspace-root <work> --artifact-root <runs> --run-id <id>
    """
    import argparse

    parser = argparse.ArgumentParser(description="HOM-LLM v4 token efficiency comparison")
    parser.add_argument("--config", required=True)
    parser.add_argument("--source-workspace-root", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--index-skip-vectors", action="store_true")
    parser.add_argument("--max-prompt-chars", type=int)
    args = parser.parse_args(argv)

    result = run_token_efficiency_comparison(
        config_path=Path(args.config),
        source_workspace_root=Path(args.source_workspace_root),
        workspace_root=Path(args.workspace_root),
        artifact_root=Path(args.artifact_root),
        run_id=args.run_id,
        case_ids=tuple(args.case_id) if args.case_id else None,
        max_prompt_chars=args.max_prompt_chars,
        index_skip_vectors=bool(args.index_skip_vectors),
    )
    dump_run_result(
        Path(args.artifact_root) / result.run_id / "token_efficiency.json",
        result,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "total_cases": result.total_cases,
                "summary_metrics": result.summary_metrics,
                "artifact_root": args.artifact_root,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
