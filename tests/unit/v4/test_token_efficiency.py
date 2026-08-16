import json
from pathlib import Path

from homllm_v4.evaluation.token_efficiency import run_token_efficiency_comparison
from homllm_v4.runtime.agent_run import HomllmAgentRunResult


def _write_source_repo(root: Path) -> None:
    (root / "utils").mkdir()
    (root / "utils" / "string_tools.py").write_text(
        "def truncate_string(text, max_length, suffix='...'):\n"
        "    if len(text) <= max_length:\n"
        "        return text\n"
        "    return text[:max_length - len(suffix)] + suffix\n",
        encoding="utf-8",
    )
    (root / "utils" / "__init__.py").write_text("", encoding="utf-8")
    (root / "api").mkdir()
    (root / "api" / "routes.py").write_text(
        "def search_endpoint(query):\n    return query\n",
        encoding="utf-8",
    )
    (root / "api" / "__init__.py").write_text("", encoding="utf-8")
    (root / "README.md").write_text("documentation\n", encoding="utf-8")


def _fake_agent_runner(request):
    run_dir = Path(request.artifact_root) / request.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    session_path = run_dir / "session.json"
    trajectory_path = run_dir / "trajectory.json"
    session_path.write_text('{"session_id":"fake"}\n', encoding="utf-8")
    trajectory_path.write_text(
        json.dumps(
            {
                "run_id": request.run_id,
                "steps": [
                    {"name": "repo_index", "status": "built"},
                    {"name": "grounded_answer", "status": "sufficient"},
                    {"name": "bounded_edit", "status": "verified"},
                    {"name": "verification", "status": "passed"},
                ],
                "metrics": {
                    "index": {"source_file_count": 3},
                    "planner": {
                        "prompt_char_count": 2000,
                        "evidence_context_item_count": 2,
                        "evidence_context_rendered_char_count": 1500,
                        "evidence_context_truncated": False,
                        "resolved_target_file": "utils/string_tools.py",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return HomllmAgentRunResult(
        run_id=request.run_id,
        stop_reason="verified",
        error_code=None,
        session_state_path=str(session_path),
        trajectory_path=str(trajectory_path),
        artifact_root=str(request.artifact_root),
        answer_text="ok",
        answer_provider_mode="summary",
        ask_stop_reason="sufficient",
        edit_stop_reason="verified",
        patch_attempt_count=1,
        provider_repair_attempt_count=0,
        verification_count=1,
        index_built=True,
        index_config_path=None,
        index_artifact_paths=None,
        index_metrics={"source_file_count": 3},
    )


def test_run_token_efficiency_comparison_computes_baselines_and_ratios(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    _write_source_repo(source_workspace)
    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")

    result = run_token_efficiency_comparison(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="token-eff",
        case_ids=("string-truncate-guard",),
        agent_runner=_fake_agent_runner,
    )

    assert result.run_id == "token-eff"
    assert result.total_cases == 1
    case = result.case_results[0]
    assert case.case_id == "string-truncate-guard"
    assert case.target_file == "utils/string_tools.py"
    assert case.v4_prompt_chars == 2000
    assert case.v4_evidence_item_count == 2
    assert case.v4_evidence_rendered_chars == 1500
    assert case.v4_evidence_truncated is False
    # Full file content plus the README and api module are in the repo copy.
    assert case.naive_full_file_chars > 0
    assert case.naive_full_repo_chars > case.naive_full_file_chars
    assert case.ratio_full_file > 0
    assert case.ratio_full_repo > 0
    summary = result.summary_metrics
    assert summary["case_count"] == 1
    assert summary["avg_ratio_full_repo"] > 0
    assert summary["avg_v4_prompt_chars"] == 2000.0


def test_run_token_efficiency_comparison_writes_artifacts(tmp_path: Path) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    _write_source_repo(source_workspace)
    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")

    result = run_token_efficiency_comparison(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="token-eff-art",
        case_ids=("string-truncate-guard",),
        agent_runner=_fake_agent_runner,
    )

    run_dir = tmp_path / "runs" / "token-eff-art"
    assert (run_dir / "evaluation" / "token_efficiency_summary.json").is_file()
    assert (run_dir / "token_efficiency.json").is_file()
    payload = json.loads(
        (run_dir / "token_efficiency.json").read_text(encoding="utf-8")
    )
    assert payload["run_id"] == "token-eff-art"
    assert payload["case_results"][0]["case_id"] == "string-truncate-guard"
    assert payload["summary_metrics"]["case_count"] == 1


def test_run_token_efficiency_comparison_rejects_unknown_case(tmp_path: Path) -> None:
    import pytest

    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    _write_source_repo(source_workspace)
    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_agent_benchmark_case"):
        run_token_efficiency_comparison(
            config_path=tmp_path / "config.yaml",
            source_workspace_root=source_workspace,
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="token-eff-bad",
            case_ids=("does-not-exist",),
            agent_runner=_fake_agent_runner,
        )


def test_run_token_efficiency_comparison_checks_config_existence(tmp_path: Path) -> None:
    import pytest

    source_workspace = tmp_path / "source"
    source_workspace.mkdir()

    with pytest.raises(ValueError, match="config_not_found"):
        run_token_efficiency_comparison(
            config_path=tmp_path / "config.yaml",
            source_workspace_root=source_workspace,
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="token-eff-noconf",
        )


def test_run_token_efficiency_comparison_checks_source_workspace(tmp_path: Path) -> None:
    import pytest

    (tmp_path / "config.yaml").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source_workspace_root_not_found"):
        run_token_efficiency_comparison(
            config_path=tmp_path / "config.yaml",
            source_workspace_root=tmp_path / "missing",
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="token-eff-nosrc",
        )
