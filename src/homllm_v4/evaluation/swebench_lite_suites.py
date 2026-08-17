"""SWE-bench Lite external fixtures for the v4 homllm-agent benchmark.

Each fixture is a real open-source repo checked out at the task's
``base_commit`` with the SWE-bench hidden ``test_patch`` applied and the bug
intact (FAIL_TO_PASS). The gold fix is deliberately NOT applied.

The materializer (``scripts/materialize_swebench_lite.py``) builds these
fixtures from the official ``princeton-nlp/SWE-bench_Lite`` dataset. This
module turns materialized fixtures into :class:`AgentBenchmarkCase` objects
that reuse the same ``homllm-agent`` loop, per-case source workspace, and
quality gate as the internal benchmark -- the only difference from the
internal suite is the *source repo* each case works on.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from homllm_v4.evaluation.agent_benchmark import AgentBenchmarkCase

FIXTURES_ROOT_DEFAULT = Path("fixtures/v4/swebench_lite")


@dataclass(frozen=True)
class SwebenchLiteFixture:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    target_files: tuple[str, ...]
    source_root: Path


def load_swebench_lite_fixtures(
    fixtures_root: Path = FIXTURES_ROOT_DEFAULT,
) -> tuple[SwebenchLiteFixture, ...]:
    """Load materialized SWE-bench Lite fixtures from ``fixtures_root``."""
    fixtures_root = Path(fixtures_root).resolve()
    if not fixtures_root.is_dir():
        raise ValueError(f"fixtures_root_not_found: {fixtures_root}")
    fixtures: list[SwebenchLiteFixture] = []
    for fixture_dir in sorted(fixtures_root.iterdir()):
        manifest_path = fixture_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            continue
        pass_to_pass_node_ids = tuple(manifest.get("pass_to_pass_node_ids", []))
        if not pass_to_pass_node_ids:
            # Fixtures materialized before node-id resolution existed: resolve
            # the raw PASS_TO_PASS names against the test files the hidden
            # test_patch touches, mirroring the FAIL_TO_PASS resolver.
            raw_names = tuple(str(x) for x in manifest.get("pass_to_pass", []))
            test_patch = str(manifest.get("test_patch", ""))
            pass_to_pass_node_ids = _resolve_test_node_ids(
                raw_names,
                _test_files_from_patch(test_patch),
            )
        fixtures.append(
            SwebenchLiteFixture(
                instance_id=str(manifest.get("instance_id", fixture_dir.name)),
                repo=str(manifest.get("repo", "")),
                base_commit=str(manifest.get("base_commit", "")),
                problem_statement=str(manifest.get("problem_statement", "")),
                fail_to_pass=tuple(manifest.get("fail_to_pass", [])),
                pass_to_pass=pass_to_pass_node_ids,
                target_files=tuple(manifest.get("target_files", [])),
                source_root=fixture_dir,
            )
        )
    if not fixtures:
        raise ValueError(f"no_swebench_fixtures_found: {fixtures_root}")
    return tuple(fixtures)


def _test_files_from_patch(patch: str) -> tuple[str, ...]:
    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git") and " b/" in line:
            path = line.split(" b/", 1)[-1]
            if "test" in path:
                files.append(path)
    return tuple(files)


def _resolve_test_node_ids(
    names: tuple[str, ...],
    test_files: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve bare SWE-bench test names to pytest node ids.

    Bare entries (e.g. ``test_Abs``) are joined with every test file the
    hidden test patch touches, mirroring the materializer's FAIL_TO_PASS
    resolution. Entries that already carry a path or ``::`` pass through.
    """
    resolved: list[str] = []
    for name in names:
        if "::" in name or "/" in name:
            resolved.append(name)
        else:
            for test_file in test_files:
                resolved.append(f"{test_file}::{name}")
    return tuple(resolved)


def _case_for_fixture(
    fixture: SwebenchLiteFixture,
    *,
    include_pass_to_pass: bool = False,
) -> AgentBenchmarkCase:
    statement = fixture.problem_statement.strip()
    target_file = fixture.target_files[0] if fixture.target_files else None
    fail_to_pass = fixture.fail_to_pass or ("hidden test",)
    verification_args: list[str] = list(fixture.fail_to_pass)
    if include_pass_to_pass:
        verification_args.extend(fixture.pass_to_pass)
    verification_argv = (
        sys.executable,
        "-m",
        "pytest",
        *verification_args,
        "-q",
    )
    metadata: dict[str, object] = {
        "verification_kind": "hidden_test",
        "swebench_instance_id": fixture.instance_id,
        "source_repo": fixture.repo,
        "base_commit": fixture.base_commit,
        "requires_localization": True,
        "fail_to_pass_count": len(fixture.fail_to_pass),
        "pass_to_pass_count": len(fixture.pass_to_pass),
        "regression_check": bool(include_pass_to_pass and fixture.pass_to_pass),
        "baseline_must_fail_argv": (
            sys.executable,
            "-m",
            "pytest",
            *fixture.fail_to_pass,
            "-q",
        ),
    }
    if include_pass_to_pass and fixture.pass_to_pass:
        metadata["baseline_must_pass_argv"] = (
            sys.executable,
            "-m",
            "pytest",
            *fixture.pass_to_pass,
            "-q",
        )
    return AgentBenchmarkCase(
        case_id=fixture.instance_id,
        query=statement,
        edit_intent=(
            "Fix the bug described in the issue so the hidden tests pass. "
            "Keep the fix minimal and localized to the relevant source file. "
            "Do not regress existing behavior: related tests must keep passing."
        ),
        expected_behavior=(
            "All of these tests must pass after the fix: " + "; ".join(fail_to_pass) + "."
        ),
        target_file=target_file,
        verification_argv=verification_argv,
        source_workspace_root=fixture.source_root,
        metadata=metadata,
    )


def swebench_lite_cases(
    fixtures_root: Path = FIXTURES_ROOT_DEFAULT,
    case_ids: tuple[str, ...] | None = None,
    include_pass_to_pass: bool = False,
) -> tuple[AgentBenchmarkCase, ...]:
    """Build agent benchmark cases from materialized SWE-bench fixtures.

    Pass ``include_pass_to_pass=True`` to also verify the SWE-bench
    PASS_TO_PASS tests, guarding against fixes that pass the target test but
    regress existing behavior.
    """
    fixtures = load_swebench_lite_fixtures(fixtures_root)
    if case_ids is not None:
        by_id = {f.instance_id: f for f in fixtures}
        missing = tuple(cid for cid in case_ids if cid not in by_id)
        if missing:
            raise ValueError(f"unknown_swebench_case: {missing[0]}")
        fixtures = tuple(by_id[cid] for cid in case_ids)
    return tuple(
        _case_for_fixture(f, include_pass_to_pass=include_pass_to_pass)
        for f in fixtures
    )


def swebench_lite_case_metadata(
    fixtures_root: Path = FIXTURES_ROOT_DEFAULT,
    include_pass_to_pass: bool = False,
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "case_id": case.case_id,
            "query": case.query,
            "target_file": case.target_file,
            "verification": " ".join(case.verification_argv),
            "metadata": case.metadata or {},
        }
        for case in swebench_lite_cases(
            fixtures_root,
            include_pass_to_pass=include_pass_to_pass,
        )
    )
