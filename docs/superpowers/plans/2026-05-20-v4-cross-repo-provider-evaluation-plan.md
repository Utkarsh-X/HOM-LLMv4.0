# v4 Cross-Repo Provider Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the real-index provider patch benchmark so it can run more than one repository/task family, proving the harness is not hard-wired to the original `test_repo` fixture.

**Architecture:** Keep the current `eval-real-index-provider-patch` entrypoint and add a small suite-profile seam. The default suite remains the current `core` suite; a new `inventory` suite runs against a second Python fixture repository with its own target files, behavior checks, target-selection case, and no-patch baselines.

**Tech Stack:** Python dataclasses, pytest, existing v4 evaluation harness, existing provider-proposed patch runner, existing CLI.

---

## File Structure

- Modify `src/homllm_v4/evaluation/real_index_provider_suites.py` to define suite profiles, select cases by suite, expose suite-aware metadata, and add inventory-specific fake provider/verification modes.
- Modify `src/homllm_v4/cli.py` to add `--case-suite`, include it in list/preflight/run paths, and preserve existing default behavior.
- Modify `tests/unit/v4/test_real_index_provider_patch_suite.py` to cover inventory metadata, suite selection, behavior verification, target-selection metrics, and unknown suite rejection.
- Modify `tests/unit/v4/test_provider_fixture_cli.py` to cover CLI propagation of `--case-suite` and list-cases output.
- Create `fixtures/v4/inventory_service_repo/` as a second repository fixture with package files for inventory, pricing, and order fulfillment.
- Update `docs/v4_architecture/09-active-goal-completion-audit.md` after verification to record the new cross-repo evidence and remaining caveats.

## Task 1: Suite Profile Contract

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write the failing metadata test**

Add a test that expects `real_index_provider_patch_case_metadata(case_suite="inventory")` to return only inventory cases and include `case_suite`.

```python
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
```

- [x] **Step 2: Run the new test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_case_metadata_can_list_inventory_suite -q
```

Expected: fail because `real_index_provider_patch_case_metadata` does not accept `case_suite`.

- [x] **Step 3: Implement minimal suite profile selection**

Add an `INVENTORY_PROVIDER_PATCH_CASES` tuple, a `REAL_INDEX_PROVIDER_PATCH_SUITES` mapping, `_select_suite_cases(case_suite)`, update `_select_cases`, and add a `case_suite` parameter to metadata and runner APIs.

- [x] **Step 4: Run the metadata test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_case_metadata_can_list_inventory_suite -q
```

Expected: pass.

## Task 2: Inventory Fixture And Runner Behavior

**Files:**
- Create: `fixtures/v4/inventory_service_repo/inventory/__init__.py`
- Create: `fixtures/v4/inventory_service_repo/inventory/items.py`
- Create: `fixtures/v4/inventory_service_repo/pricing/__init__.py`
- Create: `fixtures/v4/inventory_service_repo/pricing/discounts.py`
- Create: `fixtures/v4/inventory_service_repo/orders/__init__.py`
- Create: `fixtures/v4/inventory_service_repo/orders/fulfillment.py`
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write the failing inventory runner test**

Add a test that runs the inventory suite against the new fixture and asserts behavior cases fail baselines but pass after provider patches.

```python
def test_real_index_provider_patch_suite_runs_inventory_case_family(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root / "configs" / "agentic" / "ccg_stage2_canary_v1" / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "fixtures" / "v4" / "inventory_service_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="inventory-provider-suite",
        planner_builder=build_fake_planner,
        case_suite="inventory",
    )

    assert result.total_cases == 4
    assert result.passed_cases == 4
    assert result.summary_metrics["baseline_case_count"] == 3
    assert result.summary_metrics["categorical_metric_counts"]["target_selection_decision"] == {
        "selected": 1,
        "supplied": 3,
    }
```

- [x] **Step 2: Run the new test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_inventory_case_family -q
```

Expected: fail because the fixture and inventory patch/verification modes do not exist.

- [x] **Step 3: Add the inventory fixture repository**

Create the fixture files with intentionally small bugs:

```python
# inventory/items.py
def normalize_sku(sku: str) -> str:
    return sku.upper()
```

```python
# pricing/discounts.py
def calculate_discount(price: float, rate: float) -> float:
    return price * rate
```

```python
# orders/fulfillment.py
def fulfillment_status(order: dict[str, object]) -> str:
    if order.get("cancelled"):
        return "cancelled"
    if order.get("shipped"):
        return "shipped"
    return "pending"
```

- [x] **Step 4: Add fake provider and verification modes**

Add provider modes:

- `inventory_sku_strip_normalization`: replace `return sku.upper()` with `return sku.strip().upper()`.
- `pricing_negative_discount_guard`: replace `return price * rate` with a guard returning `0.0` for negative rates.

Add verification modes:

- `inventory_sku_strip_normalization`: assert `normalize_sku(" sku-1 ") == "SKU-1"`.
- `pricing_negative_discount_guard`: assert `calculate_discount(100, -0.2) == 0.0` and positive discounts still work.

- [x] **Step 5: Run the inventory runner test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_inventory_case_family -q
```

Expected: pass.

## Task 3: CLI Suite Selection

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write failing CLI tests**

Add tests that assert `--case-suite inventory` is propagated for normal runs and `--list-cases`.

```python
def test_cli_propagates_real_index_case_suite(monkeypatch, capsys) -> None:
    captured = {}

    def fake_suite(**kwargs):
        captured.update(kwargs)
        return _fake_eval_result()

    monkeypatch.setattr("homllm_v4.cli.run_real_index_provider_patch_suite", fake_suite)

    result = main([
        "eval-real-index-provider-patch",
        "--config", "cfg.yaml",
        "--source-workspace-root", "fixtures/v4/inventory_service_repo",
        "--workspace-root", "work",
        "--artifact-root", "runs",
        "--case-suite", "inventory",
    ])

    assert result == 0
    assert captured["case_suite"] == "inventory"
```

- [x] **Step 2: Run the CLI test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_propagates_real_index_case_suite -q
```

Expected: fail because `--case-suite` is not accepted.

- [x] **Step 3: Implement CLI argument propagation**

Add `--case-suite default="core"` and pass it to metadata, prompt preflight, and run calls.

- [x] **Step 4: Run CLI tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_propagates_real_index_case_suite tests\unit\v4\test_provider_fixture_cli.py::test_cli_lists_real_index_inventory_cases -q
```

Expected: pass.

## Task 4: Verification And Evidence Update

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run focused verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: all tests pass.

- [x] **Step 2: Build a temporary inventory index and run the inventory CLI smoke**

Create a temporary config from `configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml` whose `indexer.storage` paths point under `temp/v4_inventory_indexes_<run>`, then build that index:

```powershell
.\.venv\Scripts\python.exe runtime\index_repo.py --repo fixtures\v4\inventory_service_repo --config temp\v4_inventory_index_config_<run>.yaml --skip-vectors --json --progress-interval 1
```

The separate config is required because v3 retrieval reads index paths from config; `--source-workspace-root` controls copied workspaces only and does not switch retrieval indexes.

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config temp\v4_inventory_index_config_<run>.yaml --source-workspace-root fixtures\v4\inventory_service_repo --workspace-root temp\v4_inventory_provider_patch_work_<run> --artifact-root temp\v4_inventory_provider_patch_runs_<run> --run-id inventory-provider-fake-smoke-<run> --case-suite inventory --smoke-safe
```

Expected: JSON with `4 passed_cases`, `0 failed_cases`, and `baseline_case_count=3`.

- [x] **Step 3: Run broader v4 verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: pass.

- [x] **Step 4: Update active-goal audit**

Record the second repository suite as progress, but keep the goal incomplete because this is still a local Python fixture and not an external live benchmark or product-grade UX/sandbox.
