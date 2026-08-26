"""Unit tests for the SWE-bench campaign orchestrator's pure logic."""

import importlib.util
import json
import sys
from pathlib import Path

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

    # The drop is durable: a reload must not resurrect the stale verdict.
    reloaded = _make_ledger(tmp_path)
    assert reloaded.has_verdict("django__django-14017", "s1") is False

    # Invalidation with nothing to drop must not touch the file.
    before = (tmp_path / "ledger.json").read_text(encoding="utf-8")
    assert campaign.invalidate_records(reloaded, ["also-missing"]) == [
        "also-missing (no record)"
    ]
    assert (tmp_path / "ledger.json").read_text(encoding="utf-8") == before
