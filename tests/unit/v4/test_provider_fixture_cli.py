import json
import sys
from pathlib import Path

from homllm_v4.contracts.evaluation import EvaluationRunResult
from homllm_v4.cli import main


def test_cli_runs_provider_proposed_fixture_suite(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = main(
        [
            "eval-fixture-provider-patch",
            "--fixture-root",
            str(repo_root / "fixtures" / "v4" / "python_patch_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "provider-cli-test",
        ]
    )

    assert result == 0
    assert (tmp_path / "runs" / "provider-cli-test" / "evaluation" / "summary.json").is_file()


def test_cli_runs_agent_task_with_live_defaults(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class Result:
        run_id = "agent-cli-test"
        stop_reason = "verified"
        error_code = None
        artifact_root = str(tmp_path / "runs")
        patch_attempt_count = 1
        provider_repair_attempt_count = 0
        verification_count = 1
        planner_metrics = {"provider_tokens_in": 10}

    def fake_run(request):
        captured["request"] = request
        return Result()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("homllm_v4.cli.run_agent_task", fake_run)

    result = main(
        [
            "agent-task",
            "--config",
            "config.yaml",
            "--workspace-root",
            str(tmp_path),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--query",
            "fix normalize whitespace",
            "--intent",
            "Strip whitespace before uppercasing.",
            "--expected-behavior",
            "normalize(' sku ') returns 'SKU'.",
            "--target-file",
            "sku.py",
            "--verification-cmd",
            f"{sys.executable} -m compileall -q sku.py",
            "--live-api-key-env",
            "GOOGLE_API_KEY",
        ]
    )

    assert result == 0
    request = captured["request"]
    assert request.live_model == "gemini-3.1-flash-lite-preview"
    assert request.live_api_key == "test-key"
    assert request.target_file == "sku.py"
    assert request.provider_repair_attempts == 1
    assert request.verification_argv[-3:] == ("compileall", "-q", "sku.py")


def test_cli_preserves_windows_verification_command(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class Result:
        run_id = "agent-cli-windows-command-test"
        stop_reason = "verified"
        error_code = None
        artifact_root = str(tmp_path / "runs")
        patch_attempt_count = 1
        provider_repair_attempt_count = 0
        verification_count = 1
        planner_metrics: dict[str, object] = {}

    def fake_run(request):
        captured["request"] = request
        return Result()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("homllm_v4.cli.run_agent_task", fake_run)

    verification_cmd = (
        r"E:\HOM-LLM(v3.0)\.venv\Scripts\python.exe "
        "-c \"from inventory.items import normalize_sku; "
        "raise SystemExit(0 if normalize_sku(' sku-1 ') == 'SKU-1' else 1)\""
    )

    result = main(
        [
            "agent-task",
            "--config",
            "config.yaml",
            "--workspace-root",
            str(tmp_path),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--query",
            "fix normalize whitespace",
            "--intent",
            "Strip whitespace before uppercasing.",
            "--expected-behavior",
            "normalize_sku(' sku-1 ') returns 'SKU-1'.",
            "--target-file",
            "inventory/items.py",
            "--verification-cmd",
            verification_cmd,
            "--live-api-key-env",
            "GOOGLE_API_KEY",
        ]
    )

    assert result == 0
    request = captured["request"]
    assert request.verification_argv == (
        r"E:\HOM-LLM(v3.0)\.venv\Scripts\python.exe",
        "-c",
        "from inventory.items import normalize_sku; "
        "raise SystemExit(0 if normalize_sku(' sku-1 ') == 'SKU-1' else 1)",
    )


def test_cli_runs_agent_task_with_index_prep_flags(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class Result:
        run_id = "agent-cli-index-test"
        stop_reason = "verified"
        error_code = None
        artifact_root = str(tmp_path / "runs")
        patch_attempt_count = 1
        provider_repair_attempt_count = 0
        verification_count = 1
        planner_metrics: dict[str, object] = {}
        index_built = True
        index_config_path = str(tmp_path / "runs" / "agent-cli-index-test" / "index" / "generated_config.yaml")
        index_artifact_paths = {"artifacts": str(tmp_path / "runs" / "agent-cli-index-test" / "index")}
        index_metrics = {"source_file_count": 1}

    def fake_run(request):
        captured["request"] = request
        return Result()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("homllm_v4.cli.run_agent_task", fake_run)

    result = main(
        [
            "agent-task",
            "--config",
            "config.yaml",
            "--workspace-root",
            str(tmp_path),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--query",
            "fix normalize whitespace",
            "--intent",
            "Strip whitespace before uppercasing.",
            "--expected-behavior",
            "normalize(' sku ') returns 'SKU'.",
            "--target-file",
            "sku.py",
            "--verification-cmd",
            f"{sys.executable} -m compileall -q sku.py",
            "--live-api-key-env",
            "GOOGLE_API_KEY",
            "--prepare-index",
            "--index-artifact-dir",
            str(tmp_path / "custom-index"),
            "--index-incremental",
            "--index-skip-vectors",
        ]
    )

    assert result == 0
    request = captured["request"]
    assert request.prepare_index is True
    assert request.index_artifact_dir == tmp_path / "custom-index"
    assert request.index_incremental is True
    assert request.index_skip_vectors is True


def test_cli_runs_real_index_provider_patch_suite(monkeypatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    captured: dict[str, object] = {}
    monkeypatch.setenv("HOMLLM_TEST_KEY", "test-key")

    def fake_suite(**kwargs) -> EvaluationRunResult:
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id="real-index-cli-test",
            total_cases=3,
            passed_cases=3,
            failed_cases=0,
            case_results=(),
            summary_metrics={"stop_reason_counts": {"verified": 3}},
        )

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "real-index-cli-test",
            "--smoke-safe",
            "--edit-provider-mode",
            "live",
            "--live-provider",
            "gemini",
            "--live-model",
            "gemini-live-test",
            "--live-max-output-tokens",
            "8192",
            "--live-api-key-env",
            "HOMLLM_TEST_KEY",
            "--max-prompt-chars",
            "12345",
            "--case-id",
            "admin-routes-noop",
        ]
    )

    assert result == 0
    assert captured["config_path"].name == "ccg_stage2_agentic_ro3.yaml"
    assert captured["source_workspace_root"].name == "test_repo"
    assert captured["run_id"] == "real-index-cli-test"
    assert captured["smoke_safe"] is True
    assert captured["edit_provider_mode"] == "live"
    assert captured["live_provider_name"] == "gemini"
    assert captured["live_model"] == "gemini-live-test"
    assert captured["live_max_output_tokens"] == 8192
    assert captured["live_api_key"] == "test-key"
    assert captured["max_prompt_chars"] == 12345
    assert captured["case_ids"] == ("admin-routes-noop",)
    assert captured["case_suite"] == "core"


def test_cli_propagates_real_index_case_suite(monkeypatch, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    captured: dict[str, object] = {}

    def fake_suite(**kwargs) -> EvaluationRunResult:
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id="inventory-real-index-cli-test",
            total_cases=4,
            passed_cases=4,
            failed_cases=0,
            case_results=(),
            summary_metrics={"stop_reason_counts": {"verified": 4}},
        )

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "fixtures" / "v4" / "inventory_service_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--case-suite",
            "inventory",
        ]
    )

    assert result == 0
    assert captured["case_suite"] == "inventory"


def test_cli_runs_real_index_provider_patch_prompt_preflight_without_live_provider_call(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    captured: dict[str, object] = {}
    monkeypatch.setenv("HOMLLM_TEST_KEY", "test-key")

    def fake_suite(**kwargs) -> EvaluationRunResult:
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id="real-index-prompt-preflight-test",
            total_cases=1,
            passed_cases=0,
            failed_cases=1,
            case_results=(),
            summary_metrics={
                "error_code_counts": {"provider_prompt_budget_exceeded": 1},
                "numeric_metric_totals": {
                    "prompt_char_count": 1234,
                    "provider_tokens_in": 0,
                    "provider_tokens_out": 0,
                },
            },
        )

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main(
        [
            "eval-real-index-provider-patch",
            "--prompt-preflight",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "real-index-prompt-preflight-test",
            "--smoke-safe",
            "--edit-provider-mode",
            "live",
            "--live-provider",
            "gemini",
            "--live-model",
            "gemini-live-test",
            "--live-api-key-env",
            "HOMLLM_TEST_KEY",
            "--case-id",
            "admin-routes-noop",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert captured["edit_provider_mode"] == "fake"
    assert captured["live_api_key"] is None
    assert captured["max_prompt_chars"] == 0
    assert captured["case_ids"] == ("admin-routes-noop",)
    assert captured["case_suite"] == "core"
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["preflight_only"] is True
    assert payload["requested_edit_provider_mode"] == "live"
    assert payload["live_provider"] == "gemini"
    assert payload["live_model"] == "gemini-live-test"
    assert payload["live_api_key_env"] == "HOMLLM_TEST_KEY"
    assert payload["live_api_key_present"] is True
    assert payload["summary_metrics"]["numeric_metric_totals"]["prompt_char_count"] == 1234


def test_cli_passes_provider_repair_attempts_to_real_index_provider_patch_suite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    captured: dict[str, object] = {}

    def fake_suite(**kwargs) -> EvaluationRunResult:
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id="real-index-repair-cli-test",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            case_results=(),
            summary_metrics={"stop_reason_counts": {"verified": 1}},
        )

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "real-index-repair-cli-test",
            "--case-id",
            "string-truncate-guard",
            "--provider-repair-attempts",
            "1",
        ]
    )

    assert result == 0
    assert captured["provider_repair_attempts"] == 1


def test_cli_passes_direct_provider_planner_context_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    captured: dict[str, object] = {}

    def fake_suite(**kwargs) -> EvaluationRunResult:
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id="real-index-direct-provider-cli-test",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            case_results=(),
            summary_metrics={"stop_reason_counts": {"verified": 1}},
        )

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "real-index-direct-provider-cli-test",
            "--planner-context-mode",
            "direct-provider",
        ]
    )

    assert result == 0
    assert captured["planner_context_mode"] == "direct_provider"


def test_cli_passes_direct_provider_target_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    captured: dict[str, object] = {}

    def fake_suite(**kwargs) -> EvaluationRunResult:
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id="real-index-direct-provider-target-source-cli-test",
            total_cases=1,
            passed_cases=0,
            failed_cases=1,
            case_results=(),
            summary_metrics={"error_code_counts": {"direct_provider_target_required": 1}},
        )

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "real-index-direct-provider-target-source-cli-test",
            "--planner-context-mode",
            "direct-provider",
            "--direct-provider-target-source",
            "planner",
        ]
    )

    assert result == 1
    assert captured["direct_provider_target_source"] == "planner"


def test_cli_reports_real_index_live_mode_missing_key_as_json(
    capsys,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "missing-key-cli-test",
            "--edit-provider-mode",
            "live",
            "--case-id",
            "admin-routes-noop",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["error_code"] == "live_provider_api_key_required"


def test_cli_reports_real_index_unknown_case_id_as_json(
    capsys,
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = main(
        [
            "eval-real-index-provider-patch",
            "--config",
            str(
                repo_root
                / "configs"
                / "agentic"
                / "ccg_stage2_canary_v1"
                / "ccg_stage2_agentic_ro3.yaml"
            ),
            "--source-workspace-root",
            str(repo_root / "test_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "unknown-case-cli-test",
            "--case-id",
            "does-not-exist",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["error_code"] == "unknown_case_ids"


def test_cli_lists_real_index_provider_patch_cases(capsys) -> None:
    result = main(["eval-real-index-provider-patch", "--list-cases"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["case_count"] >= 6
    assert any(case["case_id"] == "admin-routes-noop" for case in payload["cases"])
    assert any(
        case["case_id"] == "validate-email-local-dot-guard"
        for case in payload["cases"]
    )


def test_cli_lists_real_index_inventory_cases(capsys) -> None:
    result = main(
        [
            "eval-real-index-provider-patch",
            "--list-cases",
            "--case-suite",
            "inventory",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["case_suite"] == "inventory"
    assert payload["case_count"] == 4
    assert {
        case["case_id"]
        for case in payload["cases"]
    } == {
        "inventory-sku-strip-normalization",
        "pricing-negative-discount-guard",
        "inventory-sku-strip-normalization-target-selection",
        "order-fulfillment-noop",
    }
