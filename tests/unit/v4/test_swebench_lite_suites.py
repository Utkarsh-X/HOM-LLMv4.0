import json
from pathlib import Path
import pytest

from homllm_v4.evaluation.swebench_lite_suites import (
    _resolve_test_node_ids,
    load_swebench_lite_fixtures,
    swebench_lite_cases,
    swebench_lite_case_metadata,
)


def _create_mock_fixture(
    fixture_dir: Path,
    instance_id: str,
    *,
    pass_to_pass: list[str] | None = None,
    pass_to_pass_node_ids: list[str] | None = None,
    test_patch: str = "",
    fail_to_pass: list[str] | None = None,
) -> None:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "instance_id": instance_id,
        "repo": "sympy/sympy",
        "base_commit": "abcdef123456",
        "problem_statement": "Recursion error in complexes.py",
        "fail_to_pass": fail_to_pass
        or ["sympy/functions/elementary/tests/test_complexes.py::test_issue_21627"],
        "target_files": ["sympy/functions/elementary/complexes.py"],
    }
    if pass_to_pass is not None:
        manifest["pass_to_pass"] = pass_to_pass
    if pass_to_pass_node_ids is not None:
        manifest["pass_to_pass_node_ids"] = pass_to_pass_node_ids
    if test_patch:
        manifest["test_patch"] = test_patch
    (fixture_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (fixture_dir / "module.py").write_text("VALUE = 1\n", encoding="utf-8")


def test_resolve_test_node_ids_joins_bare_names_and_passes_qualified() -> None:
    test_files = ("sympy/tests/test_complexes.py",)
    assert _resolve_test_node_ids((), test_files) == ()
    assert _resolve_test_node_ids(("test_abs",), ()) == ()
    assert _resolve_test_node_ids(("test_abs",), test_files) == (
        "sympy/tests/test_complexes.py::test_abs",
    )
    assert _resolve_test_node_ids(
        ("test_abs", "sympy/tests/test_other.py::test_sign", "already/path.py"),
        test_files,
    ) == (
        "sympy/tests/test_complexes.py::test_abs",
        "sympy/tests/test_other.py::test_sign",
        "already/path.py",
    )


def test_expected_behavior_names_all_fail_to_pass_tests(tmp_path: Path) -> None:
    # The model is told which tests the verification runs. Naming only the
    # first FAIL_TO_PASS leaves a budget model blind to the other acceptance
    # tests it must satisfy.
    fixtures_root = tmp_path / "fixtures"
    fixture_dir = fixtures_root / "sympy__sympy-21627"
    _create_mock_fixture(
        fixture_dir,
        "sympy__sympy-21627",
        fail_to_pass=[
            "sympy/functions/elementary/tests/test_complexes.py::test_issue_21627",
            "sympy/functions/elementary/tests/test_complexes.py::test_sign",
        ],
    )

    case = swebench_lite_cases(fixtures_root)[0]

    assert "test_issue_21627" in case.expected_behavior
    assert "test_sign" in case.expected_behavior
    assert case.expected_behavior.startswith("All of these tests must pass")


def test_pass_to_pass_verification_extends_pytest_argv(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    fixture_dir = fixtures_root / "sympy__sympy-21627"
    _create_mock_fixture(
        fixture_dir,
        "sympy__sympy-21627",
        pass_to_pass=["test_re", "test_im"],
        pass_to_pass_node_ids=[
            "sympy/functions/elementary/tests/test_complexes.py::test_re",
            "sympy/functions/elementary/tests/test_complexes.py::test_im",
        ],
    )

    case = swebench_lite_cases(fixtures_root)[0]
    f2p_only = [arg for arg in case.verification_argv if "::" in str(arg)]
    assert f2p_only == [
        "sympy/functions/elementary/tests/test_complexes.py::test_issue_21627"
    ]
    assert case.metadata["regression_check"] is False
    assert case.metadata["pass_to_pass_count"] == 2

    case_with_regression = swebench_lite_cases(
        fixtures_root,
        include_pass_to_pass=True,
    )[0]
    node_args = [
        arg
        for arg in case_with_regression.verification_argv
        if "::" in str(arg)
    ]
    assert node_args == [
        "sympy/functions/elementary/tests/test_complexes.py::test_issue_21627",
        "sympy/functions/elementary/tests/test_complexes.py::test_re",
        "sympy/functions/elementary/tests/test_complexes.py::test_im",
    ]
    assert case_with_regression.metadata["regression_check"] is True


def test_pass_to_pass_resolved_from_raw_names_for_legacy_fixtures(
    tmp_path: Path,
) -> None:
    fixtures_root = tmp_path / "fixtures"
    fixture_dir = fixtures_root / "sympy__sympy-21627"
    # Legacy manifest: no pass_to_pass_node_ids, only raw names + test_patch.
    _create_mock_fixture(
        fixture_dir,
        "sympy__sympy-21627",
        pass_to_pass=["test_re", "test_im"],
        test_patch=(
            "diff --git a/sympy/functions/elementary/tests/test_complexes.py "
            "b/sympy/functions/elementary/tests/test_complexes.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        ),
    )

    fixture = load_swebench_lite_fixtures(fixtures_root)[0]
    assert fixture.pass_to_pass == (
        "sympy/functions/elementary/tests/test_complexes.py::test_re",
        "sympy/functions/elementary/tests/test_complexes.py::test_im",
    )
    case = swebench_lite_cases(fixtures_root, include_pass_to_pass=True)[0]
    assert case.metadata["pass_to_pass_count"] == 2


def test_pass_to_pass_prefers_resolved_node_ids_from_manifest(
    tmp_path: Path,
) -> None:
    fixtures_root = tmp_path / "fixtures"
    fixture_dir = fixtures_root / "sympy__sympy-21627"
    _create_mock_fixture(
        fixture_dir,
        "sympy__sympy-21627",
        pass_to_pass=["test_re"],
        pass_to_pass_node_ids=["resolved/test.py::test_re"],
    )

    fixture = load_swebench_lite_fixtures(fixtures_root)[0]
    assert fixture.pass_to_pass == ("resolved/test.py::test_re",)


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
