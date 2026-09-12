"""SWE-bench Lite campaign orchestrator for host machines with tight RAM.

Runs eval-swebench-lite one case per Python process (native segfaults under
memory pressure then cost one index build, not the batch), gated by a free-RAM
pre-flight, with optional GPU/RAM telemetry sampling per case. State lives in
a JSON ledger so multiple short windows accumulate progress across days.

Typical window usage:
    python scripts/run_swebench_campaign.py --time-budget-min 210
Dry-run (prints the plan, runs nothing):
    python scripts/run_swebench_campaign.py --dry-run

Queue priority in auto mode:
  1. casualties  - cases whose previous attempt died environmentally (segfault)
  2. paired      - Stage 2 agentic_loop re-runs of the stratified 12 for
                   per-case comparison against their Stage 1 verdicts
  3. breadth     - remaining Stage 1 single_shot corpus cases

Gold-unfit cases (GOLD_UNFIT_CASES: no patch can turn FAIL_TO_PASS green on
this host) are excluded from every queue; --include-unfit overrides one.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO_ROOT / "temp" / "mvp" / "runs"
CORPUS_IDS_PATH = REPO_ROOT / "temp" / "corpus_ids.json"
DEFAULT_CONFIG = (
    "configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3_norerank.yaml"
)

STRATIFIED_12 = (
    "django__django-10914",
    "django__django-12113",
    "django__django-14017",
    "pallets__flask-4045",
    "psf__requests-2148",
    "pydata__xarray-3364",
    "sphinx-doc__sphinx-7686",
    "sphinx-doc__sphinx-10325",
    "sympy__sympy-12454",
    "sympy__sympy-16106",
    "sympy__sympy-19007",
    "sympy__sympy-21614",
)

# Cases killed by host-RAM native crashes on 2026-08-25/26 night sweeps
# (exit 139/0xC0000005 during index build). Seeded into fresh ledgers so the
# first window retries them first; their verdicts replace these stubs.
KNOWN_ENVIRONMENTAL_CRASHES = (
    "sphinx-doc__sphinx-7686",
    "sphinx-doc__sphinx-10325",
    "sympy__sympy-12454",
    "sympy__sympy-16106",
)

# Certified unfit for scoring on this host (findings doc §6.1; raw evidence:
# temp/mvp/campaign/gold_validation_results.json). For each, NO patch can turn
# FAIL_TO_PASS green here because the blocker sits outside the task diff —
# interpreter-era semantics, Windows path handling, or assertions inside
# unpatched test-helper code. Dropped from every queue so a window cannot burn
# API tokens on an unscoreable fixture; --include-unfit restores one by name
# (e.g. the Windows-only entry may be scoreable on a Linux host).
GOLD_UNFIT_CASES = {
    "django__django-11133": (
        "interpreter-era mismatch: py3.11 memoryview is iterable, so "
        "HttpResponse content iteration chunks differently than the "
        "checkout-era Python; even the upstream one-line fix (#30294) cannot "
        "satisfy the FAIL_TO_PASS assertions on this toolchain"
    ),
    "django__django-11583": (
        "Windows-only OS-layer failure (_getfinalpathname: embedded null "
        "character in path) inside code the task diff does not touch"
    ),
    "django__django-15902": (
        "whole-file fallback resolution drags ~10 environment-sensitive "
        "sibling tests into the must-pass set (RemovedInDjango50Warning "
        "default.html template warnings, Jinja2 renderer variants); the "
        "targeted fix alone cannot green the file-level FAIL_TO_PASS id"
    ),
    "pydata__xarray-3364": (
        "numpy-era writeable-flag assertion inside unpatched test helper "
        "create_test_data ('assert all(obj.data.flags.writeable ...)') "
        "fails on modern numpy; fixing it would mean editing test content"
    ),
}

# Windows native fatal exit codes (access violation, stack overflow, abort...)
CRASH_EXIT_CODES = {
    139,
    134,
    3221225477,  # 0xC0000005 access violation
    3221226505,  # 0xC0000409 stack buffer overrun
    3221225621,  # 0xC0000095 integer divide overflow
}


def is_environmental_crash(
    exit_code: int | None, verdict: str | None, timed_out: bool
) -> bool:
    """True when a native crash (never a clean timebox) yielded no verdict."""
    if timed_out or verdict:
        return False
    return exit_code is None or exit_code < 0 or exit_code in CRASH_EXIT_CODES


# --------------------------------------------------------------------------
# Host memory queries (ctypes; avoids a psutil dependency)
# --------------------------------------------------------------------------

class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD),
        ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


def free_ram_mb() -> int:
    stat = _MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return int(stat.ullAvailPhys // (1024 * 1024))


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_rss_mb(pid: int) -> int | None:
    """Working set of a process by pid; None when it has already exited."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return None
    try:
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        return int(counters.WorkingSetSize // (1024 * 1024)) if ok else None
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    ]


def descendant_pids(root_pid: int) -> list[int]:
    """All pids below root_pid in the live process tree (snapshot-based).

    Needed because the venv's python.exe is a small launcher that executes
    the base interpreter as its own child — the real workload's RSS lives
    one hop down.
    """
    TH32CS_SNAPPROCESS = 0x2
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (-1, 0xFFFFFFFFFFFFFFFF):
        return []
    links: list[tuple[int, int]] = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            links.append((entry.th32ProcessID, entry.th32ParentProcessID))
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    family = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent_pid in links:
            if parent_pid in family and pid not in family:
                family.add(pid)
                changed = True
    family.discard(root_pid)
    return sorted(family)


def process_tree_rss_mb(pid: int) -> int | None:
    """Summed working set of pid and all live descendants; None if gone."""
    total = process_rss_mb(pid)
    if total is None:
        return None
    for child_pid in descendant_pids(pid):
        total += process_rss_mb(child_pid) or 0
    return total


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------

@dataclass
class CaseRecord:
    case_id: str
    stage: str
    run_id: str
    exit_code: int | None = None
    verdict: str | None = None
    crash: bool = False
    timed_out: bool = False
    duration_s: float | None = None
    peak_rss_mb: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    finished_at: str | None = None


class Ledger:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                # Never silently discard accumulated campaign history.
                raise SystemExit(
                    f"campaign ledger {path} is corrupt ({exc}); "
                    f"inspect/restore it manually before running a window"
                ) from exc
            self.records: dict[str, CaseRecord] = {
                item["case_id"]: CaseRecord(**item)
                for item in raw.get("records", [])
            }
            self.invalidated: set[str] = set(raw.get("invalidated_case_ids", []))
        else:
            self.records = {}
            self.invalidated = set()

    def save(self) -> None:
        if self.read_only:
            # Dry-runs must observe state without mutating it.
            return
        payload = {
            "records": [vars(record) for record in self.records.values()],
            "invalidated_case_ids": sorted(self.invalidated),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        # Atomic swap so a mid-write crash cannot truncate campaign history.
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def has_verdict(self, case_id: str, stage: str) -> bool:
        record = self.records.get(case_id)
        return bool(record and record.stage == stage and record.verdict)

    def put(self, record: CaseRecord) -> None:
        self.records[record.case_id] = record
        # A completed attempt under the current harness supersedes any
        # earlier invalidation of this case.
        self.invalidated.discard(record.case_id)
        self.save()


def invalidate_records(ledger: Ledger, case_ids: list[str]) -> list[str]:
    """Drop stored verdicts so the named cases re-run under the current harness.

    A verdict recorded under an older harness revision is not evidence about
    the current one (e.g. django-14017 scored verification_failed against a
    byte-exact gold patch before the fixture DB-bootstrap fix). The drop is
    DURABLE: each id is also tombstoned in the ledger so a later start's
    seed pass cannot resurrect the stale run-dir verdict before the case
    gets to re-run. Tombstones clear when a fresh completed record lands
    (Ledger.put). Returns one human-readable line per requested id.
    """
    dropped = []
    changed = False
    for case_id in case_ids:
        record = ledger.records.pop(case_id, None)
        dropped.append(case_id if record else f"{case_id} (no record)")
        if case_id not in ledger.invalidated:
            ledger.invalidated.add(case_id)
            changed = True
    if changed or dropped:
        ledger.save()
    return dropped


def seed_ledger_from_runs(ledger: Ledger, log) -> None:
    """Import verdicts from earlier per-case run dirs (Stage 1 families)."""
    seeded = 0
    skipped_invalidated = [
        case_id for case_id in sorted(ledger.invalidated) if case_id not in ledger.records
    ]
    if skipped_invalidated:
        log(
            "invalidation tombstones honored (stale verdicts NOT re-imported): "
            + ", ".join(skipped_invalidated)
        )
    # Crash stubs go in AFTER the disk scan so a recovered verdict from a
    # later window always wins over its placeholder.
    def _seed_crash_stubs() -> int:
        stubs = 0
        for case_id in KNOWN_ENVIRONMENTAL_CRASHES:
            if case_id in ledger.invalidated:
                continue
            if case_id not in ledger.records:
                ledger.records[case_id] = CaseRecord(
                    case_id=case_id,
                    stage="s1",
                    run_id="(night-sweep-crash)",
                    crash=True,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
                stubs += 1
        return stubs
    for result_path in RUNS_ROOT.glob("swe-s1*-edit/response/write_verify_loop_result.json"):
        case_dir = result_path.parents[1]
        name = case_dir.name[len("swe-s1") :]
        # <anything>-<case_id>-edit where case_id contains the repo prefix
        case_id = None
        for known in STRATIFIED_12:
            if name.startswith(f"-{known}-") or name.endswith(f"-{known}-edit"):
                suffix = f"-{known}-edit"
                if name.endswith(suffix):
                    case_id = known
                    break
        if case_id is None:
            # generic parse: strip trailing "-edit", split on first "-" after
            # the leading dash blob; SWE-bench ids contain "__" so find that.
            stripped = name[: -len("-edit")] if name.endswith("-edit") else name
            marker = stripped.find("__")
            if marker == -1:
                continue
            org_start = stripped.rfind("-", 0, marker)
            candidate = stripped[org_start + 1 :] if org_start != -1 else stripped
            case_id = candidate
        if case_id in ledger.records or case_id in ledger.invalidated:
            continue
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ledger.put(
            CaseRecord(
                case_id=case_id,
                stage="s1",
                run_id=case_dir.name[: -len("-edit")],
                exit_code=0,
                verdict=str(result.get("stop_reason")),
                crash=False,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        )
        seeded += 1
    seeded += _seed_crash_stubs()
    if seeded:
        log(f"seeded {seeded} record(s) from previous run dirs / crash history")


# --------------------------------------------------------------------------
# Queues
# --------------------------------------------------------------------------

def corpus_ids() -> list[str]:
    if CORPUS_IDS_PATH.exists():
        return list(json.loads(CORPUS_IDS_PATH.read_text(encoding="utf-8")))
    raise SystemExit(
        f"missing {CORPUS_IDS_PATH}; regenerate via eval-swebench-lite --list-cases"
    )


def build_queue(
    stage_mode: str,
    ledger: Ledger,
    limit: int | None,
    unfit_cases: frozenset[str] | set[str] = frozenset(),
    first: tuple[str, ...] | list[str] = (),
) -> list[tuple[str, str]]:
    """Return ordered (queue_name, case_id) work items.

    Ids named in ``unfit_cases`` are dropped from every queue before the
    limit cut — they are gold-validation-certified unscoreable (see
    GOLD_UNFIT_CASES), so spending a window slot on one is pure waste.
    Ids named in ``first`` are hoisted ahead of everything else, in the
    exact order given (each keeps its earliest natural occurrence's queue
    tag; later duplicate occurrences stay in place), so a short window
    spends its minutes on the scientifically urgent re-scores first.
    """
    items: list[tuple[str, str]] = []
    if stage_mode in ("auto", "casualties"):
        casualties = [
            case_id
            for case_id in STRATIFIED_12
            if case_id in ledger.records
            and ledger.records[case_id].crash
            and not ledger.has_verdict(case_id, "s1")
        ]
        items += [("casualties", case_id) for case_id in casualties]
    if stage_mode in ("auto", "paired"):
        items += [
            ("paired", case_id)
            for case_id in STRATIFIED_12
            if not ledger.has_verdict(case_id, "s2")
        ]
    if stage_mode in ("auto", "breadth"):
        done_s1 = {
            case_id
            for case_id in ledger.records
            if ledger.records[case_id].stage == "s1" and ledger.records[case_id].verdict
        }
        items += [
            ("breadth", case_id)
            for case_id in corpus_ids()
            if case_id not in done_s1
        ]
    if unfit_cases:
        items = [item for item in items if item[1] not in unfit_cases]
    if first:
        first_occurrence: dict[str, tuple[int, tuple[str, str]]] = {}
        for index, item in enumerate(items):
            first_occurrence.setdefault(item[1], (index, item))
        hoisted: list[tuple[str, str]] = []
        seen: set[str] = set()
        for name in first:  # user-specified priority order wins
            entry = first_occurrence.get(name)
            if entry is not None and name not in seen:
                hoisted.append(entry[1])
                seen.add(name)
        # Remove exactly the hoisted occurrences; later duplicates stay put.
        rest = [
            item
            for index, item in enumerate(items)
            if item[1] not in seen or index != first_occurrence[item[1]][0]
        ]
        items = hoisted + rest
    if limit is not None:
        items = items[:limit]
    return items


# --------------------------------------------------------------------------
# Telemetry
# --------------------------------------------------------------------------

class Telemetry:
    """Samples child-process RSS, free RAM and GPU into a per-case CSV."""

    def __init__(self, csv_path: Path, pid_fn) -> None:
        self.csv_path = csv_path
        self.pid_fn = pid_fn
        self._stop = threading.Event()
        self.peak_rss_mb = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _loop(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self.csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ts_s", "child_rss_mb", "free_ram_mb", "gpu_util_pct", "gpu_mem_mb"])
            while not self._stop.is_set():
                pid = self.pid_fn()
                rss = process_tree_rss_mb(pid) if pid else None
                if rss:
                    self.peak_rss_mb = max(self.peak_rss_mb, rss)
                gpu_util, gpu_mem = _gpu_sample()
                writer.writerow([
                    round(time.monotonic(), 1),
                    rss or "",
                    free_ram_mb(),
                    gpu_util,
                    gpu_mem,
                ])
                handle.flush()
                self._stop.wait(5.0)


_GPU_QUERY = ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"]


def _gpu_sample() -> tuple[str, str]:
    try:
        out = subprocess.run(
            _GPU_QUERY, capture_output=True, text=True, timeout=10
        ).stdout.strip().splitlines()
        if out:
            util, mem = out[0].split(",")
            return util.strip(), mem.strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return "", ""


def kill_tree(pid: int) -> None:
    """Kill a process and all its children (orphaned pytest/node otherwise)."""
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True,
        timeout=30,
    )


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

def build_case_cmd(
    args: argparse.Namespace,
    stage: str,
    case_id: str,
    run_id: str,
    workspace_root: Path,
) -> list[str]:
    """Assemble one eval-swebench-lite invocation.

    The interpreter path MUST be absolute: with ``cwd`` handed to
    CreateProcess, a relative executable is not resolved against the parent's
    working directory (WinError 2) — this killed every rehearsal launch until
    pinned down.
    """
    planner_flags = (
        ["--planner-mode", "agentic_loop", "--max-agent-turns", str(args.max_agent_turns)]
        if stage == "s2"
        else []
    )
    return [
        str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
        "runtime/v4_cli.py",
        "eval-swebench-lite",
        "--fixtures-root", "fixtures/v4/swebench_lite",
        "--config", DEFAULT_CONFIG,
        "--workspace-root", str(workspace_root),
        "--artifact-root", "temp/mvp/runs",
        "--run-id", run_id,
        # fake = deterministic canned provider: exercises the full
        # orchestrator loop (telemetry, ledger, budgets) with zero API
        # tokens; live remains the default for real windows.
        "--edit-provider-mode", args.edit_provider_mode,
        "--answer-provider-mode", "summary",
        "--live-api-key-env", "OPENROUTER_API_KEY",
        "--live-provider", "openrouter",
        "--live-model", args.live_model,
        "--provider-repair-attempts", str(args.provider_repair_attempts),
        "--case-id", case_id,
        *planner_flags,
    ]


class CampaignRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.progress_path = REPO_ROOT / "temp" / "mvp" / "campaign" / "progress.log"
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.deadline = datetime.now() + timedelta(minutes=args.time_budget_min)

    def log(self, message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        with self.progress_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def wait_for_ram(self, needed_mb: int, max_minutes: float) -> bool:
        deadline = datetime.now() + timedelta(minutes=max_minutes)
        while datetime.now() < deadline:
            free = free_ram_mb()
            if free >= needed_mb:
                return True
            self.log(f"ram-wait free={free}MB need={needed_mb}MB")
            time.sleep(60)
        return free_ram_mb() >= needed_mb

    def run_case(self, queue: str, case_id: str) -> CaseRecord:
        args = self.args
        stage = "s2" if queue == "paired" else "s1"
        seq = int(time.time())
        run_id = f"sweep-{seq}-{case_id.split('-')[-1]}"
        workspace_root = REPO_ROOT / "temp" / "mvp" / "work_sweep" / run_id
        cmd = build_case_cmd(args, stage, case_id, run_id, workspace_root)
        if args.verify_baseline:
            cmd.append("--verify-baseline")

        env = dict(os.environ)
        env["OPENROUTER_API_KEY"] = args.api_key
        out_log = REPO_ROOT / "temp" / f"{run_id}.out.log"
        err_log = REPO_ROOT / "temp" / f"{run_id}.err.log"

        self.log(f"{queue}/{stage} START {case_id} rid={run_id}")
        started = time.monotonic()
        timed_out = False
        with out_log.open("w", encoding="utf-8") as out_h, err_log.open("w", encoding="utf-8") as err_h:
            proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=out_h, stderr=err_h, env=env)
            telemetry = Telemetry(REPO_ROOT / "temp" / "mvp" / "campaign" / f"{run_id}.telemetry.csv", lambda: proc.pid)
            telemetry.start()
            try:
                exit_code = proc.wait(timeout=args.per_case_timeout_min * 60)
            except subprocess.TimeoutExpired:
                timed_out = True
                self.log(f"timebox {case_id}: killing process tree after {args.per_case_timeout_min}min")
                kill_tree(proc.pid)
                try:
                    exit_code = proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    exit_code = None
            telemetry.stop()
        duration = time.monotonic() - started

        verdict = None
        result_path = RUNS_ROOT / f"{run_id}-{case_id}-edit" / "response" / "write_verify_loop_result.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                verdict = result.get("stop_reason")
            except (OSError, ValueError):
                pass
        crash = is_environmental_crash(exit_code, verdict, timed_out)
        record = CaseRecord(
            case_id=case_id,
            stage=stage,
            run_id=run_id,
            exit_code=exit_code,
            verdict=verdict,
            crash=crash,
            timed_out=timed_out,
            duration_s=round(duration, 1),
            peak_rss_mb=telemetry.peak_rss_mb or None,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        self._attach_tokens(record, run_id)
        self.log(
            f"{queue}/{stage} EXIT {case_id} code={exit_code} verdict={verdict} "
            f"crash={crash} dur={record.duration_s}s peak_rss={record.peak_rss_mb}"
        )
        return record

    def _attach_tokens(self, record: CaseRecord, run_id: str) -> None:
        summary_path = RUNS_ROOT / run_id / "evaluation" / "summary.json"
        if not summary_path.exists():
            return
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            totals = summary["summary_metrics"]["numeric_metric_totals"]
            record.tokens_in = int(totals.get("provider_tokens_in", 0))
            record.tokens_out = int(totals.get("provider_tokens_out", 0))
        except (OSError, ValueError, KeyError):
            pass

    def run(self) -> None:
        args = self.args
        # Dry-runs observe planning without mutating stored campaign state:
        # seeding and invalidation still shape the in-memory plan, but every
        # save() becomes a no-op.
        ledger = Ledger(Path(args.state), read_only=args.dry_run)
        seed_ledger_from_runs(ledger, self.log)
        if args.invalidate:
            dropped = invalidate_records(ledger, list(args.invalidate))
            self.log(f"invalidate: re-queued under current harness -> {', '.join(dropped)}")
        unfit = {
            case_id
            for case_id in GOLD_UNFIT_CASES
            if case_id not in (args.include_unfit or ())
        }
        first = tuple(args.first or ())
        items = build_queue(
            args.stages, ledger, args.limit, unfit_cases=unfit, first=first
        )
        if unfit:
            self.log(
                f"gold-unfit: skipping {len(unfit)} case(s) this window "
                f"({', '.join(sorted(unfit))}); override via --include-unfit"
            )
        if first:
            # Hoisted items occupy the true prefix; collect distinct members
            # rather than slicing by count so partially-matched --first lists
            # report their ignored names correctly.
            honored: list[str] = []
            for _queue, case_id in items:
                if case_id in first and case_id not in honored:
                    honored.append(case_id)
            unknown = [name for name in first if name not in honored]
            if honored:
                self.log(f"hoisted to front: {', '.join(honored)}")
            if unknown:
                self.log(f"note: --first ignored (not in queue): {', '.join(unknown)}")
        est = {"casualties": args.est_single_min, "paired": args.est_agentic_min, "breadth": args.est_single_min}
        self.log(
            f"plan stages={args.stages} budget={args.time_budget_min}min "
            f"items={len(items)} deadline={self.deadline.isoformat(timespec='seconds')}"
        )
        outcomes = {"verified": 0, "unverified": 0, "crashed": 0, "deferred": 0}
        for index, (queue, case_id) in enumerate(items, 1):
            remaining_budget = (self.deadline - datetime.now()).total_seconds() / 60
            projected = est[queue] + args.buffer_min
            if remaining_budget < projected:
                self.log(
                    f"budget-stop at item {index}/{len(items)} ({case_id}): "
                    f"{remaining_budget:.0f}min left < {projected:.0f}min needed"
                )
                break
            if not args.dry_run and not self.wait_for_ram(
                args.min_free_ram_mb, args.ram_wait_min
            ):
                self.log(f"ram-giveup {case_id}: deferring to next window")
                outcomes["deferred"] += 1
                continue
            if args.dry_run:
                self.log(f"dry-run would execute {queue} {case_id}")
                continue
            record = self.run_case(queue, case_id)
            ledger.put(record)
            if record.crash:
                self.log(f"note {case_id}: environmental crash; will retry next window")
                outcomes["crashed"] += 1
            elif record.verdict == "verified":
                outcomes["verified"] += 1
            else:
                outcomes["unverified"] += 1
        left = len(items) - index if items else 0
        self.log(
            "WINDOW DONE "
            + " ".join(f"{key}={val}" for key, val in outcomes.items())
            + f" items_left={left}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time-budget-min", type=int, default=210)
    parser.add_argument("--stages", choices=("auto", "casualties", "paired", "breadth"), default="auto")
    parser.add_argument("--limit", type=int, help="cap number of cases attempted this window")
    parser.add_argument("--min-free-ram-mb", type=int, default=3500)
    parser.add_argument("--ram-wait-min", type=float, default=30)
    parser.add_argument("--per-case-timeout-min", type=float, default=75)
    parser.add_argument("--buffer-min", type=float, default=10)
    parser.add_argument("--est-single-min", type=float, default=20)
    parser.add_argument("--est-agentic-min", type=float, default=35)
    parser.add_argument("--max-agent-turns", type=int, default=14)
    parser.add_argument("--provider-repair-attempts", type=int, default=1)
    parser.add_argument("--no-verify-baseline", dest="verify_baseline", action="store_false")
    parser.add_argument(
        "--edit-provider-mode",
        choices=("live", "fake"),
        default="live",
        help="fake = deterministic canned provider, zero API tokens — for "
        "rehearsing the orchestrator loop itself (pair with --limit 1)",
    )
    parser.add_argument("--live-model", default="stealth/ox-alpha")
    parser.add_argument("--api-key", default=os.environ.get("OPENROUTER_API_KEY", ""))
    parser.add_argument("--state", default=str(REPO_ROOT / "temp/mvp/campaign/ledger.json"))
    parser.add_argument(
        "--invalidate",
        action="append",
        metavar="CASE_ID",
        help="drop the stored verdict for this case so it re-runs under the "
        "current harness (repeatable; use after harness fixes)",
    )
    parser.add_argument(
        "--include-unfit",
        action="append",
        metavar="CASE_ID",
        help="force-include a gold-unfit case from GOLD_UNFIT_CASES this "
        "window (repeatable; e.g. the Windows-only exclusion may be "
        "scoreable on a Linux host)",
    )
    parser.add_argument(
        "--first",
        action="append",
        metavar="CASE_ID",
        help="hoist this case's earliest queued run to the front of the "
        "plan (repeatable; use to spend short-window minutes on the most "
        "urgent re-scores first)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.api_key:
        parser.error("OPENROUTER_API_KEY must be set or passed via --api-key")
    CampaignRunner(args).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
