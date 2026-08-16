import argparse
import json
import os
import shlex
from pathlib import Path
from typing import Sequence

from homllm_v4.api import (
    HomllmAgentRunRequest,
    AgentSessionRequest,
    AgentTaskRequest,
    agent_benchmark_case_metadata,
    real_index_provider_patch_case_metadata,
    run_homllm_agent,
    run_homllm_agent_benchmark,
    run_agent_session,
    run_agent_task,
    run_python_patch_fixture_suite,
    run_python_provider_patch_fixture_suite,
    run_real_index_provider_patch_suite,
    run_read_only_query,
    run_token_efficiency_comparison,
)


def _error_code(exc: ValueError) -> str:
    return str(exc).split(":", 1)[0]


def _split_verification_cmd(command: str) -> tuple[str, ...]:
    parts = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        parts = [_strip_wrapping_quotes(part) for part in parts]
    return tuple(parts)


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HOM-LLM v4 runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    read_only = subparsers.add_parser("read-only", help="run a v4 read-only query")
    read_only.add_argument("--config", required=True)
    read_only.add_argument("--workspace-root", required=True)
    read_only.add_argument("--query", required=True)
    read_only.add_argument("--run-id")
    read_only.add_argument("--artifact-root")
    read_only.add_argument("--max-passes", type=int, default=1)
    read_only.add_argument("--smoke-safe", action="store_true")
    homllm_agent = subparsers.add_parser(
        "homllm-agent",
        help="headless HOM-LLM coding-agent commands",
    )
    homllm_agent_subparsers = homllm_agent.add_subparsers(
        dest="agent_command",
        required=True,
    )
    homllm_agent_run = homllm_agent_subparsers.add_parser(
        "run",
        help="run the headless v4 MVP coding-agent loop",
    )
    homllm_agent_run.add_argument("--config", required=True)
    homllm_agent_run.add_argument("--workspace-root", required=True)
    homllm_agent_run.add_argument("--artifact-root", required=True)
    homllm_agent_run.add_argument("--run-id")
    homllm_agent_run.add_argument("--query", required=True)
    homllm_agent_run.add_argument("--max-passes", type=int, default=1)
    homllm_agent_run.add_argument("--smoke-safe", action="store_true")
    homllm_agent_run.add_argument("--edit-intent")
    homllm_agent_run.add_argument("--expected-behavior")
    homllm_agent_run.add_argument("--target-file")
    homllm_agent_run.add_argument("--verification-cmd")
    homllm_agent_run.add_argument("--live-provider", default="gemini")
    homllm_agent_run.add_argument(
        "--live-model",
        default="gemini-3.1-flash-lite-preview",
    )
    homllm_agent_run.add_argument("--live-max-output-tokens", type=int, default=8192)
    homllm_agent_run.add_argument("--live-api-key-env")
    homllm_agent_run.add_argument(
        "--answer-provider-mode",
        choices=("summary", "live"),
        default="summary",
    )
    homllm_agent_run.add_argument("--max-prompt-chars", type=int, default=22000)
    homllm_agent_run.add_argument("--provider-repair-attempts", type=int, default=1)
    homllm_agent_run.add_argument("--prepare-index", action="store_true")
    homllm_agent_run.add_argument("--index-artifact-dir")
    homllm_agent_run.add_argument("--index-incremental", action="store_true")
    homllm_agent_run.add_argument("--index-skip-vectors", action="store_true")
    agent_session = subparsers.add_parser(
        "agent-session",
        help="run a v4 local session: grounded ask plus optional bounded edit",
    )
    agent_session.add_argument("--config", required=True)
    agent_session.add_argument("--workspace-root", required=True)
    agent_session.add_argument("--artifact-root", required=True)
    agent_session.add_argument("--run-id")
    agent_session.add_argument("--query", required=True)
    agent_session.add_argument("--max-passes", type=int, default=1)
    agent_session.add_argument("--smoke-safe", action="store_true")
    agent_session.add_argument("--edit-intent")
    agent_session.add_argument("--expected-behavior")
    agent_session.add_argument("--target-file")
    agent_session.add_argument("--verification-cmd")
    agent_session.add_argument("--live-provider", default="gemini")
    agent_session.add_argument("--live-model", default="gemini-3.1-flash-lite-preview")
    agent_session.add_argument("--live-max-output-tokens", type=int, default=8192)
    agent_session.add_argument("--live-api-key-env")
    agent_session.add_argument(
        "--answer-provider-mode",
        choices=("summary", "live"),
        default="summary",
    )
    agent_session.add_argument("--max-prompt-chars", type=int, default=22000)
    agent_session.add_argument("--provider-repair-attempts", type=int, default=1)
    agent_session.add_argument("--prepare-index", action="store_true")
    agent_session.add_argument("--index-artifact-dir")
    agent_session.add_argument("--index-incremental", action="store_true")
    agent_session.add_argument("--index-skip-vectors", action="store_true")
    agent_task = subparsers.add_parser(
        "agent-task",
        help="run one bounded v4 MVP coding-agent task",
    )
    agent_task.add_argument("--config", required=True)
    agent_task.add_argument("--workspace-root", required=True)
    agent_task.add_argument("--artifact-root", required=True)
    agent_task.add_argument("--run-id")
    agent_task.add_argument("--query", required=True)
    agent_task.add_argument("--intent", required=True)
    agent_task.add_argument("--expected-behavior", required=True)
    agent_task.add_argument("--target-file")
    agent_task.add_argument("--verification-cmd", required=True)
    agent_task.add_argument("--live-provider", default="gemini")
    agent_task.add_argument("--live-model", default="gemini-3.1-flash-lite-preview")
    agent_task.add_argument("--live-max-output-tokens", type=int, default=8192)
    agent_task.add_argument("--live-api-key-env", required=True)
    agent_task.add_argument("--max-prompt-chars", type=int, default=22000)
    agent_task.add_argument("--provider-repair-attempts", type=int, default=1)
    agent_task.add_argument("--smoke-safe", action="store_true")
    agent_task.add_argument("--prepare-index", action="store_true")
    agent_task.add_argument("--index-artifact-dir")
    agent_task.add_argument("--index-incremental", action="store_true")
    agent_task.add_argument("--index-skip-vectors", action="store_true")
    fixture_patch = subparsers.add_parser(
        "eval-fixture-patch",
        help="run the v4 deterministic Python patch fixture suite",
    )
    fixture_patch.add_argument("--fixture-root", required=True)
    fixture_patch.add_argument("--workspace-root", required=True)
    fixture_patch.add_argument("--artifact-root", required=True)
    fixture_patch.add_argument("--run-id")
    provider_fixture_patch = subparsers.add_parser(
        "eval-fixture-provider-patch",
        help="run the v4 provider-proposed Python patch fixture suite",
    )
    provider_fixture_patch.add_argument("--fixture-root", required=True)
    provider_fixture_patch.add_argument("--workspace-root", required=True)
    provider_fixture_patch.add_argument("--artifact-root", required=True)
    provider_fixture_patch.add_argument("--run-id")
    agent_benchmark = subparsers.add_parser(
        "eval-homllm-agent",
        help="run the internal homllm-agent benchmark suite",
    )
    agent_benchmark.add_argument("--config")
    agent_benchmark.add_argument("--source-workspace-root")
    agent_benchmark.add_argument("--workspace-root")
    agent_benchmark.add_argument("--artifact-root")
    agent_benchmark.add_argument("--run-id")
    agent_benchmark.add_argument("--list-cases", action="store_true")
    agent_benchmark.add_argument("--case-id", action="append")
    agent_benchmark.add_argument(
        "--answer-provider-mode",
        choices=("summary", "live"),
        default="summary",
    )
    agent_benchmark.add_argument("--live-provider", default="gemini")
    agent_benchmark.add_argument(
        "--live-model",
        default="gemini-3.1-flash-lite-preview",
    )
    agent_benchmark.add_argument("--live-max-output-tokens", type=int, default=8192)
    agent_benchmark.add_argument("--live-api-key-env")
    agent_benchmark.add_argument("--max-prompt-chars", type=int, default=22000)
    agent_benchmark.add_argument("--provider-repair-attempts", type=int, default=1)
    agent_benchmark.add_argument("--smoke-safe", action="store_true")
    agent_benchmark.add_argument("--index-skip-vectors", action="store_true")
    agent_benchmark.add_argument(
        "--edit-provider-mode",
        choices=("fake", "live"),
        default="live",
        help="fake = deterministic canned provider (regression only); live = Gemini",
    )
    token_efficiency = subparsers.add_parser(
        "eval-token-efficiency",
        help="compare evidence-first prompt size vs naive full-file/full-repo context",
    )
    token_efficiency.add_argument("--config", required=True)
    token_efficiency.add_argument("--source-workspace-root", required=True)
    token_efficiency.add_argument("--workspace-root", required=True)
    token_efficiency.add_argument("--artifact-root", required=True)
    token_efficiency.add_argument("--run-id")
    token_efficiency.add_argument("--case-id", action="append")
    token_efficiency.add_argument("--index-skip-vectors", action="store_true")
    token_efficiency.add_argument("--max-prompt-chars", type=int)
    real_index_provider_patch = subparsers.add_parser(
        "eval-real-index-provider-patch",
        help="run the v4 real-index provider-proposed patch suite",
    )
    real_index_provider_patch.add_argument("--config")
    real_index_provider_patch.add_argument("--source-workspace-root")
    real_index_provider_patch.add_argument("--workspace-root")
    real_index_provider_patch.add_argument("--artifact-root")
    real_index_provider_patch.add_argument("--run-id")
    real_index_provider_patch.add_argument("--smoke-safe", action="store_true")
    real_index_provider_patch.add_argument("--list-cases", action="store_true")
    real_index_provider_patch.add_argument("--prompt-preflight", action="store_true")
    real_index_provider_patch.add_argument("--case-suite", default="core")
    real_index_provider_patch.add_argument(
        "--edit-provider-mode",
        choices=("fake", "live"),
        default="fake",
    )
    real_index_provider_patch.add_argument("--live-provider", default="gemini")
    real_index_provider_patch.add_argument("--live-model", default="gemini-2.5-flash")
    real_index_provider_patch.add_argument("--live-max-output-tokens", type=int, default=2048)
    real_index_provider_patch.add_argument("--live-api-key-env")
    real_index_provider_patch.add_argument("--max-prompt-chars", type=int)
    real_index_provider_patch.add_argument("--provider-repair-attempts", type=int, default=0)
    real_index_provider_patch.add_argument(
        "--planner-context-mode",
        choices=("retrieval", "direct-provider"),
        default="retrieval",
    )
    real_index_provider_patch.add_argument(
        "--direct-provider-target-source",
        choices=("actual", "planner"),
        default="actual",
    )
    real_index_provider_patch.add_argument("--case-id", action="append")

    args = parser.parse_args(argv)
    if args.command == "read-only":
        workspace_root = Path(args.workspace_root)
        artifact_root = Path(args.artifact_root).resolve() if args.artifact_root else workspace_root.resolve() / ".homllm" / "runs"
        result = run_read_only_query(
            config_path=Path(args.config),
            workspace_root=workspace_root,
            query=args.query,
            run_id=args.run_id,
            artifact_root=artifact_root,
            max_passes=args.max_passes,
            smoke_safe=bool(args.smoke_safe),
        )
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "stop_reason": result.stop_reason,
                    "pass_count": result.pass_count,
                    "artifact_root": str(artifact_root),
                    "response_text": result.response_text,
                    "error_code": result.error.code if result.error else None,
                },
                sort_keys=True,
            )
        )
        return 1 if result.error else 0
    if args.command == "homllm-agent" and args.agent_command == "run":
        command_name = "homllm-agent run"
        if args.edit_intent and not args.verification_cmd:
            print(
                json.dumps(
                    {
                        "command": command_name,
                        "error_code": "verification_cmd_required",
                        "message": "verification command is required when edit intent is provided",
                    },
                    sort_keys=True,
                )
            )
            return 1
        if args.edit_intent and not args.live_api_key_env:
            print(
                json.dumps(
                    {
                        "command": command_name,
                        "error_code": "live_api_key_env_required",
                        "message": "live api key env is required when edit intent is provided",
                    },
                    sort_keys=True,
                )
            )
            return 1
        if args.answer_provider_mode == "live" and not args.live_api_key_env:
            print(
                json.dumps(
                    {
                        "command": command_name,
                        "error_code": "live_api_key_env_required",
                        "message": "live api key env is required when answer provider mode is live",
                    },
                    sort_keys=True,
                )
            )
            return 1
        try:
            result = run_homllm_agent(
                HomllmAgentRunRequest(
                    config_path=Path(args.config),
                    workspace_root=Path(args.workspace_root),
                    artifact_root=Path(args.artifact_root),
                    run_id=args.run_id,
                    query=args.query,
                    max_passes=args.max_passes,
                    smoke_safe=bool(args.smoke_safe),
                    answer_provider_mode=args.answer_provider_mode,
                    edit_intent=args.edit_intent,
                    expected_behavior=args.expected_behavior,
                    target_file=args.target_file,
                    verification_argv=(
                        _split_verification_cmd(args.verification_cmd)
                        if args.verification_cmd
                        else ()
                    ),
                    live_provider_name=args.live_provider,
                    live_model=args.live_model,
                    live_api_key=(
                        os.getenv(args.live_api_key_env)
                        if args.live_api_key_env
                        else None
                    ),
                    live_max_output_tokens=args.live_max_output_tokens,
                    max_prompt_chars=args.max_prompt_chars,
                    provider_repair_attempts=args.provider_repair_attempts,
                    prepare_index=bool(args.prepare_index),
                    index_artifact_dir=(
                        Path(args.index_artifact_dir)
                        if args.index_artifact_dir
                        else None
                    ),
                    index_incremental=bool(args.index_incremental),
                    index_skip_vectors=bool(args.index_skip_vectors),
                )
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "command": command_name,
                        "error_code": _error_code(exc),
                        "message": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "command": command_name,
                    "run_id": result.run_id,
                    "stop_reason": result.stop_reason,
                    "error_code": result.error_code,
                    "session_state_path": result.session_state_path,
                    "trajectory_path": result.trajectory_path,
                    "artifact_root": result.artifact_root,
                    "answer_text": result.answer_text,
                    "answer_provider_mode": result.answer_provider_mode,
                    "ask_stop_reason": result.ask_stop_reason,
                    "edit_stop_reason": result.edit_stop_reason,
                    "patch_attempt_count": result.patch_attempt_count,
                    "provider_repair_attempt_count": (
                        result.provider_repair_attempt_count
                    ),
                    "verification_count": result.verification_count,
                    "index_built": result.index_built,
                    "index_config_path": result.index_config_path,
                    "index_artifact_paths": result.index_artifact_paths,
                    "index_metrics": result.index_metrics,
                    "rollback_occurred": result.rollback_occurred,
                    "rollback_restored_count": result.rollback_restored_count,
                    "rollback_deleted_count": result.rollback_deleted_count,
                },
                sort_keys=True,
            )
        )
        edit_failed = (
            result.edit_stop_reason is not None
            and (result.edit_stop_reason != "verified" or result.error_code is not None)
        )
        return 1 if edit_failed else 0
    if args.command == "agent-session":
        if args.edit_intent and not args.verification_cmd:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": "verification_cmd_required",
                        "message": "verification command is required when edit intent is provided",
                    },
                    sort_keys=True,
                )
            )
            return 1
        if args.edit_intent and not args.live_api_key_env:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": "live_api_key_env_required",
                        "message": "live api key env is required when edit intent is provided",
                    },
                    sort_keys=True,
                )
            )
            return 1
        if args.answer_provider_mode == "live" and not args.live_api_key_env:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": "live_api_key_env_required",
                        "message": "live api key env is required when answer provider mode is live",
                    },
                    sort_keys=True,
                )
            )
            return 1
        try:
            result = run_agent_session(
                AgentSessionRequest(
                    config_path=Path(args.config),
                    workspace_root=Path(args.workspace_root),
                    artifact_root=Path(args.artifact_root),
                    run_id=args.run_id,
                    query=args.query,
                    max_passes=args.max_passes,
                    smoke_safe=bool(args.smoke_safe),
                    answer_provider_mode=args.answer_provider_mode,
                    edit_intent=args.edit_intent,
                    expected_behavior=args.expected_behavior,
                    target_file=args.target_file,
                    verification_argv=(
                        _split_verification_cmd(args.verification_cmd)
                        if args.verification_cmd
                        else ()
                    ),
                    live_provider_name=args.live_provider,
                    live_model=args.live_model,
                    live_api_key=(
                        os.getenv(args.live_api_key_env)
                        if args.live_api_key_env
                        else None
                    ),
                    live_max_output_tokens=args.live_max_output_tokens,
                    max_prompt_chars=args.max_prompt_chars,
                    provider_repair_attempts=args.provider_repair_attempts,
                    prepare_index=bool(args.prepare_index),
                    index_artifact_dir=(
                        Path(args.index_artifact_dir)
                        if args.index_artifact_dir
                        else None
                    ),
                    index_incremental=bool(args.index_incremental),
                    index_skip_vectors=bool(args.index_skip_vectors),
                )
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": _error_code(exc),
                        "message": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "command": args.command,
                    "run_id": result.run_id,
                    "ask_run_id": result.ask_run_id,
                    "ask_stop_reason": result.ask_stop_reason,
                    "answer_text": result.answer_text,
                    "answer_provider_mode": result.answer_provider_mode,
                    "answer_error_code": result.answer_error_code,
                    "answer_metrics": result.answer_metrics,
                    "edit_run_id": result.edit_run_id,
                    "edit_stop_reason": result.edit_stop_reason,
                    "edit_error_code": result.edit_error_code,
                    "artifact_root": result.artifact_root,
                    "patch_attempt_count": result.patch_attempt_count,
                    "provider_repair_attempt_count": (
                        result.provider_repair_attempt_count
                    ),
                    "verification_count": result.verification_count,
                    "planner_metrics": result.planner_metrics,
                    "index_built": result.index_built,
                    "index_config_path": result.index_config_path,
                    "index_artifact_paths": result.index_artifact_paths,
                    "index_metrics": result.index_metrics,
                    "rollback_occurred": getattr(result, "rollback_occurred", False),
                    "rollback_restored_count": getattr(result, "rollback_restored_count", 0),
                    "rollback_deleted_count": getattr(result, "rollback_deleted_count", 0),
                },
                sort_keys=True,
            )
        )
        edit_failed = (
            result.edit_stop_reason is not None
            and (result.edit_stop_reason != "verified" or result.edit_error_code is not None)
        )
        return 1 if edit_failed else 0
    if args.command == "agent-task":
        try:
            result = run_agent_task(
                AgentTaskRequest(
                    config_path=Path(args.config),
                    workspace_root=Path(args.workspace_root),
                    artifact_root=Path(args.artifact_root),
                    run_id=args.run_id,
                    query=args.query,
                    intent=args.intent,
                    expected_behavior=args.expected_behavior,
                    target_file=args.target_file,
                    verification_argv=_split_verification_cmd(args.verification_cmd),
                    live_provider_name=args.live_provider,
                    live_model=args.live_model,
                    live_api_key=os.getenv(args.live_api_key_env),
                    live_max_output_tokens=args.live_max_output_tokens,
                    max_prompt_chars=args.max_prompt_chars,
                    provider_repair_attempts=args.provider_repair_attempts,
                    smoke_safe=bool(args.smoke_safe),
                    prepare_index=bool(args.prepare_index),
                    index_artifact_dir=(
                        Path(args.index_artifact_dir)
                        if args.index_artifact_dir
                        else None
                    ),
                    index_incremental=bool(args.index_incremental),
                    index_skip_vectors=bool(args.index_skip_vectors),
                )
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": _error_code(exc),
                        "message": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "command": args.command,
                    "run_id": result.run_id,
                    "stop_reason": result.stop_reason,
                    "error_code": result.error_code,
                    "artifact_root": result.artifact_root,
                    "patch_attempt_count": result.patch_attempt_count,
                    "provider_repair_attempt_count": (
                        result.provider_repair_attempt_count
                    ),
                    "verification_count": result.verification_count,
                    "planner_metrics": result.planner_metrics,
                    "index_built": getattr(result, "index_built", False),
                    "index_config_path": getattr(result, "index_config_path", None),
                    "index_artifact_paths": getattr(
                        result,
                        "index_artifact_paths",
                        None,
                    ),
                    "index_metrics": getattr(result, "index_metrics", None),
                    "rollback_occurred": getattr(result, "rollback_occurred", False),
                    "rollback_restored_count": getattr(result, "rollback_restored_count", 0),
                    "rollback_deleted_count": getattr(result, "rollback_deleted_count", 0),
                },
                sort_keys=True,
            )
        )
        return 0 if result.stop_reason == "verified" and result.error_code is None else 1
    if args.command == "eval-fixture-patch":
        artifact_root = Path(args.artifact_root).resolve()
        result = run_python_patch_fixture_suite(
            fixture_root=Path(args.fixture_root),
            workspace_root=Path(args.workspace_root),
            artifact_root=artifact_root,
            run_id=args.run_id,
        )
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "total_cases": result.total_cases,
                    "passed_cases": result.passed_cases,
                    "failed_cases": result.failed_cases,
                    "artifact_root": str(artifact_root),
                    "summary_metrics": result.summary_metrics,
                },
                sort_keys=True,
            )
        )
        return 0 if result.failed_cases == 0 else 1
    if args.command == "eval-fixture-provider-patch":
        artifact_root = Path(args.artifact_root).resolve()
        result = run_python_provider_patch_fixture_suite(
            fixture_root=Path(args.fixture_root),
            workspace_root=Path(args.workspace_root),
            artifact_root=artifact_root,
            run_id=args.run_id,
        )
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "total_cases": result.total_cases,
                    "passed_cases": result.passed_cases,
                    "failed_cases": result.failed_cases,
                    "artifact_root": str(artifact_root),
                    "summary_metrics": result.summary_metrics,
                },
                sort_keys=True,
            )
        )
        return 0 if result.failed_cases == 0 else 1
    if args.command == "eval-homllm-agent":
        if args.list_cases:
            cases = agent_benchmark_case_metadata()
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "case_count": len(cases),
                        "cases": cases,
                    },
                    sort_keys=True,
                )
            )
            return 0
        needs_live_api_key = (
            args.answer_provider_mode == "live" or args.edit_provider_mode == "live"
        )
        missing_values = (
            ("config", args.config),
            ("source_workspace_root", args.source_workspace_root),
            ("workspace_root", args.workspace_root),
            ("artifact_root", args.artifact_root),
        )
        missing = tuple(
            name for name, value in missing_values if value is None
        )
        if needs_live_api_key and not args.live_api_key_env:
            missing += ("live_api_key_env",)
        if missing:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": "missing_required_args",
                        "missing": missing,
                    },
                    sort_keys=True,
                )
            )
            return 2
        try:
            result = run_homllm_agent_benchmark(
                config_path=Path(args.config),
                source_workspace_root=Path(args.source_workspace_root),
                workspace_root=Path(args.workspace_root),
                artifact_root=Path(args.artifact_root),
                run_id=args.run_id,
                case_ids=tuple(args.case_id) if args.case_id else None,
                answer_provider_mode=args.answer_provider_mode,
                live_provider_name=args.live_provider,
                live_model=args.live_model,
                live_api_key=os.getenv(args.live_api_key_env) if args.live_api_key_env else None,
                live_max_output_tokens=args.live_max_output_tokens,
                max_prompt_chars=args.max_prompt_chars,
                provider_repair_attempts=args.provider_repair_attempts,
                smoke_safe=bool(args.smoke_safe),
                index_skip_vectors=bool(args.index_skip_vectors),
                edit_provider_mode=args.edit_provider_mode,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": _error_code(exc),
                        "message": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "command": args.command,
                    "run_id": result.run_id,
                    "total_cases": result.total_cases,
                    "passed_cases": result.passed_cases,
                    "failed_cases": result.failed_cases,
                    "artifact_root": str(Path(args.artifact_root)),
                    "summary_metrics": result.summary_metrics,
                },
                sort_keys=True,
            )
        )
        return 0 if result.failed_cases == 0 else 1
    if args.command == "eval-token-efficiency":
        try:
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
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": _error_code(exc),
                        "message": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "command": args.command,
                    "run_id": result.run_id,
                    "total_cases": result.total_cases,
                    "artifact_root": str(Path(args.artifact_root).resolve()),
                    "summary_metrics": result.summary_metrics,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "eval-real-index-provider-patch":
        if args.list_cases:
            try:
                cases = real_index_provider_patch_case_metadata(
                    case_suite=args.case_suite
                )
            except ValueError as exc:
                print(
                    json.dumps(
                        {
                            "command": args.command,
                            "error_code": _error_code(exc),
                            "message": str(exc),
                        },
                        sort_keys=True,
                    )
                )
                return 1
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "case_suite": args.case_suite,
                        "case_count": len(cases),
                        "cases": cases,
                    },
                    sort_keys=True,
                )
            )
            return 0
        missing = tuple(
            name
            for name, value in (
                ("config", args.config),
                ("source_workspace_root", args.source_workspace_root),
                ("workspace_root", args.workspace_root),
                ("artifact_root", args.artifact_root),
            )
            if value is None
        )
        if missing:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": "missing_required_args",
                        "missing": missing,
                    },
                    sort_keys=True,
                )
            )
            return 2
        artifact_root = Path(args.artifact_root).resolve()
        if args.prompt_preflight:
            requested_live_api_key = (
                os.getenv(args.live_api_key_env) if args.live_api_key_env else None
            )
            try:
                result = run_real_index_provider_patch_suite(
                    config_path=Path(args.config),
                    source_workspace_root=Path(args.source_workspace_root),
                    workspace_root=Path(args.workspace_root),
                    artifact_root=artifact_root,
                    run_id=args.run_id,
                    smoke_safe=bool(args.smoke_safe),
                    edit_provider_mode="fake",
                    live_provider_name=args.live_provider,
                    live_model=args.live_model,
                    live_max_output_tokens=args.live_max_output_tokens,
                    live_api_key=None,
                    case_ids=tuple(args.case_id) if args.case_id else None,
                    case_suite=args.case_suite,
                    max_prompt_chars=0,
                    provider_repair_attempts=args.provider_repair_attempts,
                    planner_context_mode=args.planner_context_mode.replace("-", "_"),
                    direct_provider_target_source=args.direct_provider_target_source,
                )
            except ValueError as exc:
                print(
                    json.dumps(
                        {
                            "command": args.command,
                            "error_code": _error_code(exc),
                            "message": str(exc),
                            "preflight_only": True,
                        },
                        sort_keys=True,
                    )
                )
                return 1
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "preflight_only": True,
                        "requested_edit_provider_mode": args.edit_provider_mode,
                        "live_provider": args.live_provider,
                        "live_model": args.live_model,
                        "live_max_output_tokens": args.live_max_output_tokens,
                        "live_api_key_env": args.live_api_key_env,
                        "live_api_key_present": requested_live_api_key is not None,
                        "run_id": result.run_id,
                        "total_cases": result.total_cases,
                        "artifact_root": str(artifact_root),
                        "summary_metrics": result.summary_metrics,
                    },
                    sort_keys=True,
                )
            )
            return 0
        try:
            result = run_real_index_provider_patch_suite(
                config_path=Path(args.config),
                source_workspace_root=Path(args.source_workspace_root),
                workspace_root=Path(args.workspace_root),
                artifact_root=artifact_root,
                run_id=args.run_id,
                smoke_safe=bool(args.smoke_safe),
                edit_provider_mode=args.edit_provider_mode,
                live_provider_name=args.live_provider,
                live_model=args.live_model,
                live_max_output_tokens=args.live_max_output_tokens,
                live_api_key=os.getenv(args.live_api_key_env) if args.live_api_key_env else None,
                case_ids=tuple(args.case_id) if args.case_id else None,
                case_suite=args.case_suite,
                max_prompt_chars=args.max_prompt_chars,
                provider_repair_attempts=args.provider_repair_attempts,
                planner_context_mode=args.planner_context_mode.replace("-", "_"),
                direct_provider_target_source=args.direct_provider_target_source,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "error_code": _error_code(exc),
                        "message": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "total_cases": result.total_cases,
                    "passed_cases": result.passed_cases,
                    "failed_cases": result.failed_cases,
                    "artifact_root": str(artifact_root),
                    "summary_metrics": result.summary_metrics,
                },
                sort_keys=True,
            )
        )
        return 0 if result.failed_cases == 0 else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
