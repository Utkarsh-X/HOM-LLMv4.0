import hashlib
import json
from pathlib import Path

import pytest

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.evaluation.real_index_provider_suites import (
    REAL_INDEX_PROVIDER_PATCH_CASES,
    _copy_baseline_workspace,
    _copy_case_workspace,
    real_index_provider_patch_case_metadata,
    run_real_index_provider_patch_suite,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanner
from homllm_v4.services.direct_read_service import DirectReadService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class FakeRetrievalService:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        if request.target_files:
            target_file = request.target_files[0]
        elif "cache" in request.query or "namespace" in request.query:
            target_file = "cache/cache_manager.py"
        elif "metrics" in request.query or "histogram" in request.query:
            target_file = "monitoring/metrics.py"
        elif "date_helpers" in request.query or "parse_date" in request.query:
            target_file = "utils/date_helpers.py"
        elif "job_queue" in request.query or "async_jobs" in request.query:
            target_file = "async_jobs/job_queue.py"
        elif "validate" in request.query or "validator" in request.query:
            target_file = "utils/validators.py"
        elif "inventory" in request.query or "sku" in request.query:
            target_file = "inventory/items.py"
        elif "pricing" in request.query or "discount" in request.query:
            target_file = "pricing/discounts.py"
        else:
            target_file = "utils/string_tools.py"
        content = (self.workspace_root / target_file).read_text(encoding="utf-8")
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=EvidenceSet(
                evidence_set_id=f"{request.task_id}:evidence",
                query=request.query,
                candidates=(
                    EvidenceCandidate(
                        candidate_id=f"{request.task_id}:candidate:{target_file}",
                        file_path=target_file,
                        symbol_id=None,
                        span_start=1,
                        span_end=max(1, len(content.splitlines())),
                        content_hash=content_hash(content),
                        source_channels=("fake",),
                        bm25_score=None,
                        vector_score=None,
                        graph_score=None,
                        retrieval_score=1.0,
                        metadata={"task_id": request.task_id},
                    ),
                ),
                diagnostics=RetrievalDiagnostics(
                    bm25_count=1,
                    vector_count=0,
                    graph_added_count=0,
                    precision_added_count=0,
                    coverage_added_count=0,
                    retrieval_disagreement=None,
                    degraded=False,
                    degradation_reason=None,
                ),
            ),
            error=None,
            telemetry=None,
            artifacts=(),
        )


def build_fake_planner(
    *,
    config_path: Path,
    workspace_root: Path,
    edit_provider,
    smoke_safe: bool = True,
    artifact_manager=None,
    max_prompt_chars: int | None = None,
) -> ProviderProposedPatchPlanner:
    return ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(Path(workspace_root)),
        direct_read_service=DirectReadService(workspace_root=Path(workspace_root)),
        edit_proposer=ProviderBackedEditProposer(
            provider=edit_provider,
            artifact_manager=artifact_manager,
            max_prompt_chars=max_prompt_chars,
        ),
        )


def test_copy_case_workspace_ignores_python_cache_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    cache_dir = source / "pkg" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (source / "pkg" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (cache_dir / "module.cpython-313.pyc").write_bytes(b"volatile")

    copied = _copy_case_workspace(
        source_workspace_root=source,
        workspace_root=tmp_path / "work",
        run_id="copy-cache-ignore",
        case_id="case-a",
    )

    assert (copied / "pkg" / "module.py").is_file()
    assert not (copied / "pkg" / "__pycache__").exists()


def test_copy_baseline_workspace_ignores_python_cache_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    cache_dir = source / "pkg" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (source / "pkg" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (cache_dir / "module.cpython-313.pyc").write_bytes(b"volatile")

    copied = _copy_baseline_workspace(
        source_workspace_root=source,
        workspace_root=tmp_path / "work",
        run_id="baseline-cache-ignore",
        case_id="case-a",
    )

    assert (copied / "pkg" / "module.py").is_file()
    assert not (copied / "pkg" / "__pycache__").exists()


def test_real_index_provider_patch_case_metadata_can_list_inventory_suite() -> None:
    metadata = real_index_provider_patch_case_metadata(case_suite="inventory")

    case_ids = {case["case_id"] for case in metadata}
    assert case_ids == {
        "inventory-sku-strip-normalization",
        "pricing-negative-discount-guard",
        "inventory-sku-strip-normalization-target-selection",
        "order-fulfillment-noop",
    }
    assert {case["case_suite"] for case in metadata} == {"inventory"}


def test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="real-index-provider-suite",
        planner_builder=build_fake_planner,
    )

    assert result.total_cases >= 6
    assert result.passed_cases == result.total_cases
    assert result.failed_cases == 0
    assert result.summary_metrics["stop_reason_counts"]["verified"] >= 3
    assert (
        tmp_path / "runs" / "real-index-provider-suite" / "evaluation" / "summary.json"
    ).is_file()
    semantic_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "string-truncate-guard"
        / "utils"
        / "string_tools.py"
    )
    assert "if max_length <= len(suffix):" in semantic_target.read_text(encoding="utf-8")
    file_path_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "validate-file-path-drive-guard"
        / "utils"
        / "validators.py"
    )
    assert "':' in file_path" in file_path_target.read_text(encoding="utf-8")
    selection_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "string-truncate-guard-target-selection"
        / "utils"
        / "string_tools.py"
    )
    assert "if max_length <= len(suffix):" in selection_target.read_text(encoding="utf-8")
    email_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "validate-email-local-dot-guard"
        / "utils"
        / "validators.py"
    )
    assert "'..' in local_part" in email_target.read_text(encoding="utf-8")
    date_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "parse-date-strip"
        / "utils"
        / "date_helpers.py"
    )
    assert "datetime.strptime(date_string.strip(), format_str)" in date_target.read_text(
        encoding="utf-8"
    )
    job_queue_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "job-queue-total-size-guard"
        / "async_jobs"
        / "job_queue.py"
    )
    assert "current_queue_size = sum(len(jobs) for jobs in self.pending_jobs.values())" in (
        job_queue_target.read_text(encoding="utf-8")
    )
    assert result.summary_metrics["baseline_case_count"] == 17
    numeric_totals = result.summary_metrics["numeric_metric_totals"]
    assert numeric_totals["prompt_char_count"] > 0
    assert numeric_totals["evidence_context_item_count"] >= result.total_cases
    assert numeric_totals["evidence_context_rendered_char_count"] >= 0
    assert "evidence_context_truncated" in result.summary_metrics["categorical_metric_counts"]
    truncate_case = next(
        case for case in result.case_results if case.case_id == "string-truncate-guard"
    )
    assert truncate_case.baseline_runner_id == "no_patch_baseline"
    assert truncate_case.baseline_stop_reason == "verification_failed"
    assert truncate_case.actual_stop_reason == "verified"
    assert truncate_case.metric_deltas is not None
    assert "verification_count" in truncate_case.metric_deltas
    selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "string-truncate-guard-target-selection"
    )
    assert selection_case.actual_stop_reason == "verified"
    assert selection_case.metrics["target_selection_decision"] == "selected"
    assert selection_case.metrics["resolved_target_file"] == "utils/string_tools.py"
    file_path_selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "validate-file-path-drive-guard-target-selection"
    )
    assert file_path_selection_case.actual_stop_reason == "verified"
    assert file_path_selection_case.metrics["target_selection_decision"] == "selected"
    assert file_path_selection_case.metrics["resolved_target_file"] == "utils/validators.py"
    email_selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "validate-email-local-dot-guard-target-selection"
    )
    assert email_selection_case.actual_stop_reason == "verified"
    assert email_selection_case.metrics["target_selection_decision"] == "selected"
    assert email_selection_case.metrics["resolved_target_file"] == "utils/validators.py"
    date_case = next(case for case in result.case_results if case.case_id == "parse-date-strip")
    assert date_case.baseline_stop_reason == "verification_failed"
    assert date_case.actual_stop_reason == "verified"
    job_case = next(
        case for case in result.case_results if case.case_id == "job-queue-total-size-guard"
    )
    assert job_case.baseline_stop_reason == "verification_failed"
    assert job_case.actual_stop_reason == "verified"
    date_selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "parse-date-strip-target-selection"
    )
    assert date_selection_case.actual_stop_reason == "verified"
    assert date_selection_case.metrics["target_selection_decision"] == "selected"
    assert date_selection_case.metrics["resolved_target_file"] == "utils/date_helpers.py"
    job_selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "job-queue-total-size-guard-target-selection"
    )
    assert job_selection_case.actual_stop_reason == "verified"
    assert job_selection_case.metrics["target_selection_decision"] == "selected"
    assert job_selection_case.metrics["resolved_target_file"] == "async_jobs/job_queue.py"
    assert result.summary_metrics["categorical_metric_counts"]["target_selection_decision"] == {
        "selected": 7,
        "supplied": 13,
    }
    assert result.summary_metrics["baseline_case_count"] == 17
    noop_case = next(case for case in result.case_results if case.case_id == "admin-routes-noop")
    assert noop_case.baseline_runner_id is None
    assert noop_case.baseline_stop_reason is None
    assert noop_case.metrics["target_selection_decision"] == "supplied"
    assert noop_case.metrics["resolved_target_file"] == "api/routes.py"
    prompt_artifact = (
        tmp_path
        / "runs"
        / "real-index-provider-suite"
        / "provider"
        / "string-truncate-guard"
        / "prompt.txt"
    )
    response_artifact = (
        tmp_path
        / "runs"
        / "real-index-provider-suite"
        / "provider"
        / "string-truncate-guard"
        / "response.txt"
    )
    assert prompt_artifact.is_file()
    assert response_artifact.is_file()
    assert "Expected behavior:" in prompt_artifact.read_text(encoding="utf-8")


def test_real_index_provider_patch_suite_runs_inventory_case_family(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "fixtures" / "v4" / "inventory_service_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="inventory-provider-suite",
        planner_builder=build_fake_planner,
        case_suite="inventory",
    )

    assert result.total_cases == 4
    assert result.passed_cases == 4
    assert result.failed_cases == 0
    assert result.summary_metrics["baseline_case_count"] == 3
    assert result.summary_metrics["categorical_metric_counts"][
        "target_selection_decision"
    ] == {
        "selected": 1,
        "supplied": 3,
    }
    sku_case = next(
        case
        for case in result.case_results
        if case.case_id == "inventory-sku-strip-normalization"
    )
    assert sku_case.baseline_stop_reason == "verification_failed"
    assert sku_case.actual_stop_reason == "verified"
    selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "inventory-sku-strip-normalization-target-selection"
    )
    assert selection_case.metrics["target_selection_decision"] == "selected"
    assert selection_case.metrics["resolved_target_file"] == "inventory/items.py"


def test_job_queue_cases_warn_against_reentrant_queue_size_call() -> None:
    job_queue_cases = [
        case
        for case in REAL_INDEX_PROVIDER_PATCH_CASES
        if case.provider_mode == "job_queue_size_guard"
    ]

    assert job_queue_cases
    for case in job_queue_cases:
        assert "without calling get_queue_size from inside the existing lock" in (
            case.expected_behavior
        )


def test_real_index_provider_patch_suite_includes_hard_cache_target_selection_cases() -> None:
    cases = {case.case_id: case for case in REAL_INDEX_PROVIDER_PATCH_CASES}

    assert (
        cases["cache-namespace-invalidate-target-selection"].target_file
        == "cache/cache_manager.py"
    )
    assert cases["cache-namespace-invalidate-target-selection"].planner_target_file is None
    assert cases["metrics-labelled-stats-target-selection"].target_file == "monitoring/metrics.py"
    assert cases["metrics-labelled-stats-target-selection"].planner_target_file is None


def test_real_index_provider_patch_suite_can_run_direct_provider_context_mode(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="direct-provider-context-suite",
        planner_builder=build_fake_planner,
        planner_context_mode="direct_provider",
        case_ids=("string-truncate-guard-target-selection",),
    )

    assert result.passed_cases == 1
    case = result.case_results[0]
    assert case.metrics["planner_context_mode"] == "direct_provider"
    assert case.metrics["target_selection_decision"] == "direct_supplied"
    assert case.metrics["evidence_context_item_count"] == 0
    assert case.metrics["resolved_target_file"] == "utils/string_tools.py"


def test_direct_provider_planner_target_source_exposes_missing_target_for_target_omitted_case(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="direct-provider-planner-target-source-suite",
        planner_context_mode="direct_provider",
        direct_provider_target_source="planner",
        case_ids=("cache-namespace-invalidate-target-selection",),
    )

    assert result.failed_cases == 1
    assert result.case_results[0].error_code == "direct_provider_target_required"
    assert result.summary_metrics["error_code_counts"] == {
        "direct_provider_target_required": 1
    }


def test_real_index_provider_patch_suite_records_quality_dimension_metrics(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="quality-dimension-suite",
        planner_builder=build_fake_planner,
        case_ids=(
            "admin-routes-noop",
            "cache-namespace-invalidate-target-selection",
        ),
    )

    counts = result.summary_metrics["categorical_metric_counts"]
    assert counts["quality_requires_localization"] == {"False": 1, "True": 1}
    assert counts["quality_verification_kind"] == {"behavior": 1, "compile": 1}
    assert counts["quality_provider_mode"] == {
        "cache_namespace_invalidation": 1,
        "noop": 1,
    }


def test_real_index_provider_patch_suite_runs_hard_cache_target_selection_cases(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="hard-cache-target-selection-suite",
        planner_builder=build_fake_planner,
        case_ids=(
            "cache-namespace-invalidate-target-selection",
            "metrics-labelled-stats-target-selection",
        ),
    )

    assert result.total_cases == 2
    assert result.passed_cases == 2
    assert result.summary_metrics["categorical_metric_counts"][
        "target_selection_decision"
    ] == {"selected": 2}
    assert result.summary_metrics["categorical_metric_counts"]["resolved_target_file"] == {
        "cache/cache_manager.py": 1,
        "monitoring/metrics.py": 1,
    }


def test_real_index_provider_patch_suite_can_use_injected_live_provider_builder(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    calls: list[dict[str, object]] = []

    class RecordingProvider:
        tokens_in = 3
        tokens_out = 5

        def propose_edit(self, request):
            evidence_ids = ()
            target_file = ""
            content_lines: list[str] = []
            in_content = False
            for line in request.prompt.splitlines():
                if line.startswith("Target file:"):
                    target_file = line.removeprefix("Target file:").strip()
                elif line.startswith("Evidence IDs:"):
                    evidence_ids = tuple(
                        item.strip()
                        for item in line.removeprefix("Evidence IDs:").split(",")
                        if item.strip()
                    )
                elif line == "Current content:":
                    in_content = True
                elif in_content:
                    content_lines.append(line)
            return ProviderEditProposalResponse(
                text=json.dumps(
                    {
                        "target_file": target_file,
                        "new_content": "\n".join(content_lines),
                        "rationale": "Injected live provider no-op response.",
                        "evidence_ids": list(evidence_ids),
                        "risk_flags": [],
                    }
                ),
                tokens_in=self.tokens_in,
                tokens_out=self.tokens_out,
                model="injected-live",
                metadata={"provider": "injected"},
            )

    def build_provider(**kwargs):
        calls.append(kwargs)
        return RecordingProvider()

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="live-provider-mode-suite",
        planner_builder=build_fake_planner,
        edit_provider_mode="live",
        live_provider_name="gemini",
        live_model="gemini-live-test",
        live_api_key="test-key",
        live_provider_builder=build_provider,
        live_max_output_tokens=8192,
        case_ids=("admin-routes-noop",),
    )

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert calls[0]["provider_name"] == "gemini"
    assert calls[0]["model"] == "gemini-live-test"
    assert calls[0]["api_key"] == "test-key"
    assert calls[0]["max_output_tokens"] == 8192


def test_real_index_provider_patch_suite_repairs_after_verification_failure(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    class RepairingProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def propose_edit(self, request):
            self.calls.append(request.prompt)
            target_file = ""
            evidence_ids = ()
            current_content = ""
            in_content = False
            for line in request.prompt.splitlines():
                if line.startswith("Target file:"):
                    target_file = line.removeprefix("Target file:").strip()
                elif line.startswith("Evidence IDs:"):
                    evidence_ids = tuple(
                        item.strip()
                        for item in line.removeprefix("Evidence IDs:").split(",")
                        if item.strip()
                    )
                elif line == "Current content:":
                    in_content = True
                elif in_content:
                    current_content += f"{line}\n"

            if len(self.calls) == 1:
                new_content = current_content
                rationale = "Initial no-op response should fail verification."
            else:
                old = (
                    "    if len(text) <= max_length:\n"
                    "        return text\n"
                    "    return text[:max_length - len(suffix)] + suffix\n"
                )
                new = (
                    "    if len(text) <= max_length:\n"
                    "        return text\n"
                    "    if max_length <= len(suffix):\n"
                    "        return text[:max_length]\n"
                    "    return text[:max_length - len(suffix)] + suffix\n"
                )
                new_content = current_content.replace(old, new)
                rationale = "Repair failed verification with suffix-length guard."

            return ProviderEditProposalResponse(
                text=json.dumps(
                    {
                        "target_file": target_file,
                        "new_content": new_content,
                        "rationale": rationale,
                        "evidence_ids": list(evidence_ids),
                        "risk_flags": [],
                    }
                ),
                tokens_in=100 + len(self.calls),
                tokens_out=10 + len(self.calls),
                model="repair-test",
                metadata={"provider": "repair-test"},
            )

    provider = RepairingProvider()

    def build_provider(**kwargs):
        return provider

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="repair-suite",
        planner_builder=build_fake_planner,
        edit_provider_mode="live",
        live_provider_name="gemini",
        live_model="repair-test",
        live_api_key="test-key",
        live_provider_builder=build_provider,
        case_ids=("string-truncate-guard",),
        provider_repair_attempts=1,
    )

    assert result.total_cases == 1
    assert result.passed_cases == 1
    case = result.case_results[0]
    assert case.actual_stop_reason == "verified"
    assert case.metrics["patch_attempt_count"] == 2
    assert case.metrics["provider_repair_attempt_count"] == 1
    assert case.metrics["provider_tokens_in"] == 203
    assert case.metrics["provider_tokens_out"] == 23
    assert len(provider.calls) == 2
    assert "Repair context: Previous verification stopped with reason verification_failed" in (
        provider.calls[1]
    )


def test_real_index_provider_patch_suite_surfaces_provider_invocation_failure(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    class RaisingProvider:
        def propose_edit(self, request):
            raise OSError("dns lookup failed")

    def build_provider(**kwargs):
        return RaisingProvider()

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="provider-invocation-failure-suite",
        planner_builder=build_fake_planner,
        edit_provider_mode="live",
        live_provider_name="gemini",
        live_model="invocation-failure-test",
        live_api_key="test-key",
        live_provider_builder=build_provider,
        case_ids=("admin-routes-noop",),
    )

    assert result.total_cases == 1
    assert result.failed_cases == 1
    assert result.case_results[0].error_code == "provider_invocation_failed"
    assert result.summary_metrics["error_code_counts"] == {
        "provider_invocation_failed": 1
    }
    assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_in"] == 0
    assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_out"] == 0


def test_real_index_provider_patch_suite_surfaces_provider_build_failure(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    def build_provider(**kwargs):
        raise RuntimeError("provider unavailable")

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="provider-build-failure-suite",
        planner_builder=build_fake_planner,
        edit_provider_mode="live",
        live_provider_name="gemini",
        live_model="build-failure-test",
        live_api_key="test-key",
        live_provider_builder=build_provider,
        case_ids=("admin-routes-noop",),
    )

    assert result.total_cases == 1
    assert result.failed_cases == 1
    case = result.case_results[0]
    assert case.actual_stop_reason == "patch_failed"
    assert case.error_code == "provider_invocation_failed"
    assert case.metrics["provider_tokens_in"] == 0
    assert case.metrics["provider_tokens_out"] == 0
    assert case.metrics["provider_runtime_exception_type"] == "RuntimeError"
    assert case.metrics["quality_baseline_target_knowledge"] == "retrieval_localizes"
    assert result.summary_metrics["error_code_counts"] == {
        "provider_invocation_failed": 1
    }


def test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="prompt-limit-suite",
        planner_builder=build_fake_planner,
        case_ids=("admin-routes-noop",),
        max_prompt_chars=10,
    )

    assert result.total_cases == 1
    assert result.passed_cases == 0
    assert result.failed_cases == 1
    case = result.case_results[0]
    assert case.case_id == "admin-routes-noop"
    assert case.actual_stop_reason == "patch_failed"
    assert case.error_code == "provider_prompt_budget_exceeded"
    assert case.metrics["provider_tokens_in"] == 0
    assert case.metrics["provider_tokens_out"] == 0
    assert result.summary_metrics["error_code_counts"] == {
        "provider_prompt_budget_exceeded": 1
    }
    assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_in"] == 0
    assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_out"] == 0
    assert (
        tmp_path
        / "runs"
        / "prompt-limit-suite"
        / "provider"
        / "admin-routes-noop"
        / "prompt.txt"
    ).is_file()


def test_real_index_provider_patch_suite_rejects_live_mode_without_api_key(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    with pytest.raises(ValueError, match="live_provider_api_key_required"):
        run_real_index_provider_patch_suite(
            config_path=repo_root
            / "configs"
            / "agentic"
            / "ccg_stage2_canary_v1"
            / "ccg_stage2_agentic_ro3.yaml",
            source_workspace_root=repo_root / "test_repo",
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="missing-live-key-suite",
            planner_builder=build_fake_planner,
            edit_provider_mode="live",
            live_provider_name="gemini",
            live_model="gemini-live-test",
            live_api_key=None,
            case_ids=("admin-routes-noop",),
        )


def test_real_index_provider_patch_suite_rejects_unknown_case_id(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    with pytest.raises(ValueError, match="unknown_case_ids"):
        run_real_index_provider_patch_suite(
            config_path=repo_root
            / "configs"
            / "agentic"
            / "ccg_stage2_canary_v1"
            / "ccg_stage2_agentic_ro3.yaml",
            source_workspace_root=repo_root / "test_repo",
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="unknown-case-suite",
            planner_builder=build_fake_planner,
            case_ids=("does-not-exist",),
        )
