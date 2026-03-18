import json
import subprocess
import sys
from pathlib import Path

from eval.run_regression_cluster_audit import _resolve_run_inputs


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_regression_cluster_audit_writes_markdown_and_json(tmp_path):
    run_dir = tmp_path / "eval" / "runs" / "sample_run"
    run_dir.mkdir(parents=True)
    responses_path = run_dir / "responses.jsonl"
    responses_path.write_text(
        json.dumps(
            {
                "query_id": 4,
                "query_text": "What are the job lifecycle states?",
                "status": "OK",
                "tokens_in": 100,
                "tokens_out": 200,
                "run_id": "run-123",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    generated_answers = run_dir / "generated_answers"
    generated_answers.mkdir()
    (generated_answers / "query_04.txt").write_text("answer", encoding="utf-8")

    artifacts_dir = tmp_path / "artifacts" / "runs" / "run-123"
    _write_json(
        artifacts_dir / "retrieval_diagnostics.json",
        {
            "resolved_intent": "explain",
            "intent_source": "heuristic",
            "intent_rule": "trace",
            "retrieval_stage_trace": {"final_output": 50},
            "candidates_top20": [
                {"file": "async_jobs/job_queue.py"},
                {"file": "async_jobs/worker.py"},
            ],
        },
    )
    _write_json(
        artifacts_dir / "telemetry.json",
        {
            "phases": {
                "CONTEXT": {
                    "blocks": 10,
                    "tokens": 1200,
                    "token_budget": 5200,
                    "drop_trace": [
                        {"drop_reason": "kept", "file": "async_jobs/job_queue.py"},
                        {"drop_reason": "kept", "file": "async_jobs/worker.py"},
                    ],
                },
                "CLAIM_COVERAGE": {
                    "coverage_ratio": 0.5,
                    "recovery_triggered": False,
                },
            }
        },
    )
    _write_json(
        artifacts_dir / "generation_diagnostics.json",
        {
            "hallucination_flags": ["identifier_not_in_context: fail_job"],
        },
    )

    judge_path = run_dir / "judge_results__gpt-oss-120b.jsonl"
    judge_path.write_text(
        json.dumps(
            {
                "query_id": 4,
                "verdict": "regressed",
                "explanation": "Less complete",
                "scores": {"completeness": {"candidate": 3, "baseline": 5}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "eval" / "run_regression_cluster_audit.py"),
            "--responses",
            str(responses_path),
            "--judge-results",
            str(judge_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "regression_cluster_audit.md" in result.stdout
    md_path = run_dir / "regression_cluster_audit.md"
    json_path = run_dir / "regression_cluster_audit.json"
    assert md_path.exists()
    assert json_path.exists()

    md = md_path.read_text(encoding="utf-8")
    assert "## Query 04" in md
    assert "### 1. Generated Answer" in md
    assert "`GENERATION_OVERREACH`" in md

    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["query_count"] == 1
    assert summary["queries"][0]["judge_verdict"] == "regressed"
    assert "GENERATION_OVERREACH" in summary["queries"][0]["preliminary_labels"]


def test_regression_cluster_audit_filters_selected_queries(tmp_path):
    run_dir = tmp_path / "eval" / "runs" / "sample_run"
    run_dir.mkdir(parents=True)
    responses_path = run_dir / "responses.jsonl"
    responses_path.write_text(
        "\n".join(
            [
                json.dumps({"query_id": 4, "query_text": "q4", "status": "OK", "tokens_in": 1, "tokens_out": 1, "run_id": "r4"}),
                json.dumps({"query_id": 7, "query_text": "q7", "status": "OK", "tokens_in": 1, "tokens_out": 1, "run_id": "r7"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "generated_answers").mkdir()
    (run_dir / "generated_answers" / "query_04.txt").write_text("a4", encoding="utf-8")

    for run_id in ("r4", "r7"):
        artifacts_dir = tmp_path / "artifacts" / "runs" / run_id
        _write_json(artifacts_dir / "retrieval_diagnostics.json", {"retrieval_stage_trace": {"final_output": 50}, "candidates_top20": []})
        _write_json(artifacts_dir / "telemetry.json", {"phases": {"CONTEXT": {"blocks": 1, "tokens": 1, "token_budget": 10, "drop_trace": []}, "CLAIM_COVERAGE": {"coverage_ratio": 1.0, "recovery_triggered": False}}})
        _write_json(artifacts_dir / "generation_diagnostics.json", {"hallucination_flags": []})

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "eval" / "run_regression_cluster_audit.py"),
            "--responses",
            str(responses_path),
            "--queries",
            "7",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    summary = json.loads((run_dir / "regression_cluster_audit.json").read_text(encoding="utf-8"))
    assert summary["query_count"] == 1
    assert summary["queries"][0]["query_id"] == 7


def test_regression_cluster_audit_rejects_placeholder_path():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "eval" / "run_regression_cluster_audit.py"),
            "--responses",
            r"eval/runs/<run_name>/responses.jsonl",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "replace placeholder text like <run_name>" in result.stderr or "replace placeholder text like <run_name>" in result.stdout


def test_resolve_run_inputs_supports_explicit_responses_and_placeholder_rejection(tmp_path):
    run_dir = tmp_path / "eval" / "runs" / "sample_run"
    run_dir.mkdir(parents=True)
    responses_path = run_dir / "responses.jsonl"
    responses_path.write_text(
        json.dumps({"query_id": 4, "query_text": "q4", "status": "OK", "tokens_in": 1, "tokens_out": 1, "run_id": "r4"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "generated_answers").mkdir()
    (run_dir / "generated_answers" / "query_04.txt").write_text("a4", encoding="utf-8")
    judge_path = run_dir / "judge_results__gpt-oss-120b.jsonl"
    judge_path.write_text(
        json.dumps({"query_id": 4, "verdict": "equal", "explanation": "ok", "scores": {"completeness": {"candidate": 5, "baseline": 5}}}) + "\n",
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts" / "runs" / "r4"
    _write_json(artifacts_dir / "retrieval_diagnostics.json", {"retrieval_stage_trace": {"final_output": 50}, "candidates_top20": []})
    _write_json(artifacts_dir / "telemetry.json", {"phases": {"CONTEXT": {"blocks": 1, "tokens": 1, "token_budget": 10, "drop_trace": []}, "CLAIM_COVERAGE": {"coverage_ratio": 1.0, "recovery_triggered": False}}})
    _write_json(artifacts_dir / "generation_diagnostics.json", {"hallucination_flags": []})

    resolved_responses, resolved_judge = _resolve_run_inputs(str(responses_path), None, str(judge_path))
    assert resolved_responses == responses_path.resolve()
    assert resolved_judge == judge_path.resolve()

    try:
        _resolve_run_inputs(r"eval/runs/<run_name>/responses.jsonl", None, None)
        assert False, "Expected placeholder path rejection"
    except SystemExit as exc:
        assert "replace placeholder text like <run_name>" in str(exc)
