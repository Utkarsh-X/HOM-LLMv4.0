import json
from pathlib import Path
import pytest

from homllm_v4.evaluation.swebench_lite_suites import (
    load_swebench_lite_fixtures,
    swebench_lite_cases,
    swebench_lite_case_metadata,
)


def _create_mock_fixture(fixture_dir: Path, instance_id: str) -> None:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "instance_id": instance_id,
        "repo": "sympy/sympy",
        "base_commit": "abcdef123456",
        "problem_statement": "Recursion error in complexes.py",
        "fail_to_pass": ["sympy/functions/elementary/tests/test_complexes.py::test_issue_21627"],
        "target_files": ["sympy/functions/elementary/complexes.py"],
    }
    (fixture_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (fixture_dir / "module.py").write_text("VALUE = 1\n", encoding="utf-8")


def test_load_swebench_lite_fixtures_and_cases(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    _create_mock_fixture(fixtures_root / "sympy__sympy-21627", "sympy__sympy-21627")
    _create_mock_fixture(fixtures_root / "sympy__sympy-21614", "sympy__sympy-21614")

    fixtures = load_swebench_lite_fixtures(fixtures_root)
    assert len(fixtures) == 2
    assert fixtures[0].instance_id == "sympy__sympy-21614"
    assert fixtures[1].instance_id == "sympy__sympy-21627"

    cases = swebench_lite_cases(fixtures_root)
    assert len(cases) == 2
    assert cases[0].case_id == "sympy__sympy-21614"
    assert cases[0].target_file is not None
    assert cases[0].source_workspace_root == fixtures_root / "sympy__sympy-21614"
    assert "sympy__sympy-21614" in cases[0].metadata["swebench_instance_id"]

    metadata = swebench_lite_case_metadata(fixtures_root)
    assert len(metadata) == 2
    assert metadata[0]["case_id"] == "sympy__sympy-21614"


def test_swebench_lite_cases_filtering(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    _create_mock_fixture(fixtures_root / "sympy__sympy-21627", "sympy__sympy-21627")
    _create_mock_fixture(fixtures_root / "sympy__sympy-21614", "sympy__sympy-21614")

    cases = swebench_lite_cases(fixtures_root, case_ids=("sympy__sympy-21627",))
    assert len(cases) == 1
    assert cases[0].case_id == "sympy__sympy-21627"

    with pytest.raises(ValueError, match="unknown_swebench_case"):
        swebench_lite_cases(fixtures_root, case_ids=("nonexistent_case",))


def test_swebench_lite_fixtures_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixtures_root_not_found"):
        load_swebench_lite_fixtures(tmp_path / "nonexistent")

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    with pytest.raises(ValueError, match="no_swebench_fixtures_found"):
        load_swebench_lite_fixtures(empty_root)
