"""Unit tests for the SWE-bench campaign orchestrator's pure logic."""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "run_swebench_campaign.py"
)
_spec = importlib.util.spec_from_file_location("run_swebench_campaign", _SCRIPT_PATH)
campaign = importlib.util.module_from_spec(_spec)
# Register before exec: dataclass KW_ONLY detection resolves sys.modules[name].
sys.modules[_spec.name] = campaign
_spec.loader.exec_module(campaign)


def _make_ledger(tmp_path):
    return campaign.Ledger(tmp_path / "ledger.json")


def test_ledger_roundtrip_and_has_verdict(tmp_path) -> None:
    ledger = _make_ledger(tmp_path)
    ledger.put(
        campaign.CaseRecord(
            case_id="repo__pkg-1",
            stage="s1",
            run_id="r1",
            verdict="verified",
            crash=False,
        )
    )
    ledger.put(
        campaign.CaseRecord(
            case_id="repo__pkg-2",
            stage="s2",
            run_id="r2",
            verdict=None,
            crash=True,
        )
    )

    reloaded = _make_ledger(tmp_path)
    assert reloaded.has_verdict("repo__pkg-1", "s1") is True
    # verdict is stage-specific: an s1 verdict does not satisfy an s2 request
    assert reloaded.has_verdict("repo__pkg-1", "s2") is False
    assert reloaded.has_verdict("repo__pkg-2", "s2") is False
    assert reloaded.records["repo__pkg-2"].crash is True


def test_is_environmental_crash_classification() -> None:
    # Native access-violation style exit with no verdict -> environmental.
    assert campaign.is_environmental_crash(139, None, False) is True
    assert campaign.is_environmental_crash(3221225477, None, False) is True
    assert campaign.is_environmental_crash(None, None, False) is True
    # Clean CLI exit reporting a failed case is a legitimate benchmark result.
    assert campaign.is_environmental_crash(1, "verification_failed", False) is False
    assert campaign.is_environmental_crash(0, "verified", False) is False
    # Timeboxes are never classified as native crashes.
    assert campaign.is_environmental_crash(124, None, True) is False
    assert campaign.is_environmental_crash(None, None, True) is False


def test_seed_parses_case_ids_from_run_dirs(tmp_path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    for rid, case_id in (
        ("swe-s1pc3-0825", "sphinx-doc__sphinx-7686"),
        ("swe-s1b9-9999", "django__django-12345"),
    ):
        result_dir = runs_root / f"{rid}-{case_id}-edit" / "response"
        result_dir.mkdir(parents=True)
        (result_dir / "write_verify_loop_result.json").write_text(
            json.dumps({"stop_reason": "verified"}), encoding="utf-8"
        )
    monkeypatch.setattr(campaign, "RUNS_ROOT", runs_root)

    ledger = _make_ledger(tmp_path)
    campaign.seed_ledger_from_runs(ledger, lambda _msg: None)

    assert ledger.records["sphinx-doc__sphinx-7686"].verdict == "verified"
    assert ledger.records["django__django-12345"].verdict == "verified"
    # Disk-derived verdicts win: the recovered case must not be a crash stub.
    assert ledger.records["sphinx-doc__sphinx-7686"].crash is False
    # Cases with no run dir on disk fall back to their crash-history stub.
    stubbed = [
        case_id
        for case_id in campaign.KNOWN_ENVIRONMENTAL_CRASHES
        if ledger.records[case_id].crash
    ]
    assert set(stubbed) == set(campaign.KNOWN_ENVIRONMENTAL_CRASHES) - {
        "sphinx-doc__sphinx-7686"
    }


def test_seed_seeds_known_crashes_and_skips_existing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        campaign, "RUNS_ROOT", tmp_path / "does-not-exist-runs-root"
    )
    ledger = _make_ledger(tmp_path)
    campaign.seed_ledger_from_runs(ledger, lambda _msg: None)

    crashed = campaign.KNOWN_ENVIRONMENTAL_CRASHES
    assert all(ledger.records[case_id].crash for case_id in crashed)

    # A second seeding pass must not duplicate or resurrect records.
    before = dict(ledger.records)
    campaign.seed_ledger_from_runs(ledger, lambda _msg: None)
    assert set(ledger.records) == set(before)


def test_build_queue_orders_casualties_paired_breadth(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        campaign,
        "corpus_ids",
        lambda: ["a__x-1", "a__x-2", "b__y-3"],
    )
    ledger = _make_ledger(tmp_path)
    ledger.put(
        campaign.CaseRecord(
            case_id="sphinx-doc__sphinx-7686",
            stage="s1",
            run_id="old",
            crash=True,
        )  # in STRATIFIED_12, no verdict -> casualty
    )
    ledger.put(
        campaign.CaseRecord(
            case_id="a__x-1",
            stage="s1",
            run_id="done",
            verdict="verification_failed",
        )  # breadth must skip it
    )

    queue = campaign.build_queue("auto", ledger, limit=None)
    prefixes = [queue_name for queue_name, _case in queue]
    assert prefixes[:1] == ["casualties"]
    assert queue[0] == ("casualties", "sphinx-doc__sphinx-7686")
    paired_cases = [case for name, case in queue if name == "paired"]
    assert paired_cases == list(campaign.STRATIFIED_12)
    breadth_cases = [case for name, case in queue if name == "breadth"]
    assert breadth_cases == ["a__x-2", "b__y-3"]

    limited = campaign.build_queue("auto", ledger, limit=5)
    assert len(limited) == 5


def test_invalidate_records_drops_and_reports(tmp_path) -> None:
    ledger = _make_ledger(tmp_path)
    ledger.put(
        campaign.CaseRecord(
            case_id="django__django-14017",
            stage="s1",
            run_id="stale",
            verdict="verification_failed",
        )
    )

    dropped = campaign.invalidate_records(
        ledger, ["django__django-14017", "never-recorded-case"]
    )
    assert dropped == ["django__django-14017", "never-recorded-case (no record)"]
    assert "django__django-14017" not in ledger.records

    # The drop is durable AND tombstoned: a reload must not resurrect the
    # stale verdict, even via the run-dir seeding pass.
    reloaded = _make_ledger(tmp_path)
    assert reloaded.has_verdict("django__django-14017", "s1") is False
    assert reloaded.invalidated == {"django__django-14017", "never-recorded-case"}

    # Repeating an already-applied invalidation is a no-op on disk.
    before = (tmp_path / "ledger.json").read_text(encoding="utf-8")
    assert campaign.invalidate_records(
        reloaded, ["django__django-14017", "never-recorded-case"]
    ) == ["django__django-14017 (no record)", "never-recorded-case (no record)"]
    assert (tmp_path / "ledger.json").read_text(encoding="utf-8") == before


def test_invalidation_tombstone_blocks_seed_resurrection(
    tmp_path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    result_dir = runs_root / "swe-s1b2-0825-django__django-14017-edit" / "response"
    result_dir.mkdir(parents=True)
    (result_dir / "write_verify_loop_result.json").write_text(
        json.dumps({"stop_reason": "verification_failed"}), encoding="utf-8"
    )
    monkeypatch.setattr(campaign, "RUNS_ROOT", runs_root)

    ledger = _make_ledger(tmp_path)
    campaign.seed_ledger_from_runs(ledger, lambda _msg: None)
    assert ledger.has_verdict("django__django-14017", "s1") is True  # seeded

    campaign.invalidate_records(ledger, ["django__django-14017"])

    # A later process start re-seeds from the same run dirs: the tombstone,
    # not the stale disk verdict, must win.
    reloaded = _make_ledger(tmp_path)
    seeded_logs: list[str] = []
    campaign.seed_ledger_from_runs(reloaded, seeded_logs.append)
    assert "django__django-14017" not in reloaded.records
    assert any("tombstone" in line.lower() for line in seeded_logs)

    # Without a stored verdict the case re-enters the plan...
    queue = campaign.build_queue("breadth", reloaded, limit=None)
    assert ("breadth", "django__django-14017") in queue

    # ...and a fresh completed attempt clears its own tombstone durably.
    reloaded.put(
        campaign.CaseRecord(
            case_id="django__django-14017",
            stage="s1",
            run_id="fresh",
            verdict="verified",
        )
    )
    final = _make_ledger(tmp_path)
    assert final.invalidated == set()
    assert final.records["django__django-14017"].verdict == "verified"

    # The stale run dir can never poison anything again.
    campaign.seed_ledger_from_runs(final, lambda _msg: None)
    assert final.records["django__django-14017"].run_id == "fresh"


def test_read_only_ledger_never_writes(tmp_path) -> None:
    path = tmp_path / "ledger.json"
    ledger = campaign.Ledger(path, read_only=True)
    ledger.put(
        campaign.CaseRecord(
            case_id="a__x-1", stage="s1", run_id="r", verdict="verified"
        )
    )
    ledger.invalidated.add("b__y-2")
    campaign.invalidate_records(ledger, ["c__z-3"])
    assert path.exists() is False  # dry-run purity: nothing persisted


def test_kill_tree_terminates_child_process() -> None:
    if sys.platform != "win32":
        pytest.skip("taskkill-based tree kill is Windows-specific")
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.poll() is None  # child is alive before the kill
        campaign.kill_tree(proc.pid)
        code = proc.wait(timeout=30)
        assert code != 0  # force-terminated, not a clean exit
    finally:
        if proc.poll() is None:
            proc.kill()


def test_process_tree_rss_includes_descendants() -> None:
    if sys.platform != "win32":
        pytest.skip("tool-help snapshot tree walk is Windows-specific")
    # The direct child here mirrors the venv launcher shim: a small process
    # whose interesting memory lives in its own child.
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(20)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Poll like the telemetry thread does: the descendant appears once
        # the launcher has spawned the real interpreter (~sub-second).
        import time as _time

        deadline = _time.monotonic() + 10
        rss = 0
        while _time.monotonic() < deadline:
            sample = campaign.process_tree_rss_mb(proc.pid)
            assert isinstance(sample, int)
            rss = max(rss, sample)
            if rss > 8:
                break
            _time.sleep(0.2)
        # A bare shim samples ~4MB; a real interpreter tree exceeds 8MB,
        # proving the snapshot walk reached the descendant workload.
        assert rss > 8
    finally:
        if proc.poll() is None:
            campaign.kill_tree(proc.pid)
            proc.wait(timeout=30)


def test_build_queue_stage_modes_select_only_their_queues(tmp_path) -> None:
    ledger = _make_ledger(tmp_path)
    ledger.put(
        campaign.CaseRecord(
            case_id="sphinx-doc__sphinx-7686",
            stage="s1",
            run_id="(night-sweep-crash)",
            crash=True,  # casualty stub
        )
    )

    only_casualties = campaign.build_queue("casualties", ledger, limit=None)
    assert only_casualties == [("casualties", "sphinx-doc__sphinx-7686")]

    breadth = campaign.build_queue("breadth", ledger, limit=None)
    assert [name for name, _case in breadth] == ["breadth"] * len(breadth)


def test_build_case_cmd_uses_absolute_interpreter(monkeypatch) -> None:
    monkeypatch.setattr(campaign, "REPO_ROOT", Path(__file__).resolve().parents[3])
    args = argparse.Namespace(
        max_agent_turns=14,
        edit_provider_mode="live",
        live_model="stealth/ox-alpha",
        provider_repair_attempts=1,
    )
    workspace = Path("temp/unused-workspace")

    single = campaign.build_case_cmd(
        args, "s1", "django__django-10914", "sweep-x", workspace
    )
    agentic = campaign.build_case_cmd(
        args, "s2", "django__django-10914", "sweep-x", workspace
    )

    # Windows CreateProcess does not resolve a relative executable against
    # cwd when lpCurrentDirectory is passed — the interpreter path must be
    # absolute or every window dies on its first launch.
    interpreter = Path(single[0])
    assert interpreter.is_absolute()
    assert interpreter.name == "python.exe"
    for cmd in (single, agentic):
        joined = " ".join(cmd)
        assert "--case-id django__django-10914" in joined
        assert "--edit-provider-mode live" in joined
    assert "--planner-mode" not in " ".join(single)  # s1 stays single_shot
    assert "--planner-mode agentic_loop --max-agent-turns 14" in " ".join(agentic)


def test_ledger_loads_legacy_payload_without_tombstones(tmp_path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "case_id": "a__x-1",
                        "stage": "s1",
                        "run_id": "r",
                        "verdict": "verified",
                    }
                ],
                "updated_at": "2026-08-26T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    ledger = campaign.Ledger(path)
    assert ledger.records["a__x-1"].verdict == "verified"
    assert ledger.invalidated == set()


def test_ledger_save_is_atomic_and_corruption_fails_loud(tmp_path) -> None:
    path = tmp_path / "ledger.json"
    ledger = _make_ledger(tmp_path)
    ledger.put(
        campaign.CaseRecord(
            case_id="a__x-1", stage="s1", run_id="r", verdict="verified"
        )
    )
    # Atomic swap: no half-written temp file may survive a save.
    assert not (tmp_path / "ledger.json.tmp").exists()

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text('{"records": [ truncated', encoding="utf-8")
    with pytest.raises(SystemExit, match="corrupt"):
        campaign.Ledger(corrupt)
    # The corrupt bytes themselves are left untouched for manual recovery.
    assert corrupt.read_text(encoding="utf-8") == '{"records": [ truncated'


def test_build_queue_excludes_unfit_cases_before_limit_cut(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        campaign,
        "corpus_ids",
        lambda: ["a__x-1", "django__django-11583", "b__y-2"],
    )
    ledger = _make_ledger(tmp_path)

    unfit = frozenset(["django__django-11583"])
    queue = campaign.build_queue("breadth", ledger, limit=None, unfit_cases=unfit)
    assert queue == [("breadth", "a__x-1"), ("breadth", "b__y-2")]

    # The filter precedes the limit cut, so a full slot budget survives.
    limited = campaign.build_queue("breadth", ledger, limit=2, unfit_cases=unfit)
    assert limited == [("breadth", "a__x-1"), ("breadth", "b__y-2")]

    # Unfit cases are also barred from paired re-runs of the stratified 12
    # (pydata__xarray-3364 is in both sets).
    paired = campaign.build_queue(
        "paired", ledger, limit=None, unfit_cases=frozenset(campaign.GOLD_UNFIT_CASES)
    )
    assert "pydata__xarray-3364" not in [case for _name, case in paired]

    # --include-unfit equivalent: a narrower unfit set restores the case.
    restored = campaign.build_queue(
        "breadth",
        ledger,
        limit=None,
        unfit_cases=frozenset(campaign.GOLD_UNFIT_CASES) - {"django__django-11583"},
    )
    assert ("breadth", "django__django-11583") in restored


def test_gold_unfit_cases_are_documented_and_outside_stratified_scope() -> None:
    # Every exclusion carries a human-readable root cause and exists in the
    # corpus; the paired-stage overlap is exactly the one stratified-12 case.
    assert campaign.GOLD_UNFIT_CASES  # non-empty by design
    for case_id, reason in campaign.GOLD_UNFIT_CASES.items():
        assert reason.strip()
    assert set(campaign.GOLD_UNFIT_CASES) & set(campaign.STRATIFIED_12) == {
        "pydata__xarray-3364"
    }


def test_build_queue_hoists_first_cases_ahead_of_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        campaign,
        "corpus_ids",
        lambda: ["a__x-1", "django__django-14017", "b__y-2"],
    )
    ledger = _make_ledger(tmp_path)
    # Post---invalidate state for django__django-14017: NO stored verdict, so
    # auto mode naturally schedules it twice (paired s2 + breadth s1).

    items = campaign.build_queue(
        "auto",
        ledger,
        limit=None,
        first=("django__django-14017",),
    )
    # The hoisted item is the case's earliest natural occurrence (paired s2
    # here, ahead of breadth in auto order) with its queue tag intact; the
    # rest keeps its natural order and the later breadth occurrence stays.
    assert items[0] == ("paired", "django__django-14017")
    assert items[1] == ("paired", "django__django-10914")  # STRATIFIED_12 head
    assert ("breadth", "django__django-14017") in items[1:]
    assert ("breadth", "a__x-1") in items[1:]

    # Hoist survives the limit cut (it precedes it), multiple names keep
    # their given order, and unknown names are simply ignored.
    multi = campaign.build_queue(
        "breadth", ledger, limit=2, first=("b__y-2", "a__x-1", "never__case-0")
    )
    assert multi == [("breadth", "b__y-2"), ("breadth", "a__x-1")]

    # Unfit filtering wins over hoisting: an unfit name never comes back.
    blocked = campaign.build_queue(
        "paired",
        ledger,
        limit=None,
        unfit_cases=frozenset(["pydata__xarray-3364"]),
        first=("pydata__xarray-3364", "sympy__sympy-21614"),
    )
    assert "pydata__xarray-3364" not in [case for _name, case in blocked]
    assert blocked[0] == ("paired", "sympy__sympy-21614")
