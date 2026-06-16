import json
from pathlib import Path

from homllm_v4.evaluation.fixture_suites import run_python_patch_fixture_suite


def test_python_patch_fixture_suite_runs_and_persists_summary(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixture_root = repo_root / "fixtures" / "v4" / "python_patch_repo"
    workspace_root = tmp_path / "workspaces"
    artifact_root = tmp_path / "runs"

    result = run_python_patch_fixture_suite(
        fixture_root=fixture_root,
        workspace_root=workspace_root,
        artifact_root=artifact_root,
        run_id="fixture-suite",
    )

    assert result.run_id == "fixture-suite"
    assert result.total_cases == 4
    assert result.passed_cases == 4
    assert result.failed_cases == 0
    assert result.summary_metrics["stop_reason_counts"] == {
        "patch_failed": 2,
        "repair_budget_exhausted": 1,
        "verified": 1,
    }
    summary_path = artifact_root / "fixture-suite" / "evaluation" / "summary.json"
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["summary_metrics"]["baseline_case_count"] == 0
