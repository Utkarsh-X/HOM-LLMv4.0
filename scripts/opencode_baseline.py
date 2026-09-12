"""OpenCode CLI baseline harness for SWE-bench Lite comparison runs.

Fair-comparison methodology: same tasks, same model (stealth/ox-alpha via
OpenRouter), same verification — only the agent harness differs. For each
case the harness copies the pristine fixture workspace, git-initializes it,
lets `opencode run` attempt the fix unattended, extracts the resulting patch
via `git diff`, and re-runs the case's canonical FAIL_TO_PASS verification.
Results append to a JSONL ledger beside the v4 campaign ledger.

Usage:
  export OPENROUTER_API_KEY='<key>'
  # validate provider/model/auth with one tiny message:
  python scripts/opencode_baseline.py --probe
  # attempt one or more cases:
  python scripts/opencode_baseline.py --case-id sympy__sympy-21614
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from homllm_v4.evaluation.swebench_lite_suites import (  # noqa: E402
    FIXTURES_ROOT_DEFAULT,
    swebench_lite_cases,
)


def _load_gold_unfit_cases() -> dict[str, str]:
    """Reuse the campaign orchestrator's certified-unfit exclusion set.

    Fair pairing requires both lanes to score the same case universe; a
    fixture no patch can pass must burn neither lane's tokens.
    """
    import importlib.util

    script = REPO_ROOT / "scripts" / "run_swebench_campaign.py"
    spec = importlib.util.spec_from_file_location("run_swebench_campaign", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.GOLD_UNFIT_CASES

LEDGER_PATH = REPO_ROOT / "temp" / "mvp" / "campaign" / "opencode_ledger.jsonl"
WORK_ROOT = REPO_ROOT / "temp" / "opencode_baseline"


def log(message: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def run_cmd(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def kill_tree(pid: int) -> None:
    """Kill a process and all children (opencode spawns node workers)."""
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_with_timebox(cmd: list[str], timeout_s: float, **kwargs) -> tuple[subprocess.CompletedProcess | None, bool]:
    """Run cmd; on timeout kill the whole tree. Returns (proc|None, timed_out)."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **kwargs,
    )
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = "", ""
        return subprocess.CompletedProcess(cmd, 124, out, err), True
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err), False


def opencode_prefix() -> list[str]:
    """Resolve the npm shim: CreateProcess cannot execute .cmd files directly."""
    exe = shutil.which("opencode")
    if exe is None:
        raise SystemExit("opencode not found on PATH; install via: npm install -g opencode-ai")
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe]
    return [exe]


def probe(model: str, api_key: str) -> bool:
    log("probe: sending one tiny message through opencode...")
    started = time.monotonic()
    proc, _timed_out = run_with_timebox(
        [*opencode_prefix(), "run", "-m", model, "Reply with exactly: OK"],
        timeout_s=180,
        cwd=str(REPO_ROOT),
        env=dict(os.environ, OPENROUTER_API_KEY=api_key),
    )
    duration = time.monotonic() - started
    output = (proc.stdout or "").strip()
    log(f"probe exit={proc.returncode} dur={duration:.0f}s output[:200]={output[:200]!r}")
    if proc.returncode != 0:
        log(f"probe stderr tail: {(proc.stderr or '')[-400:]}")
    return proc.returncode == 0


def prepare_workspace(case, seq: int) -> Path | None:
    target = WORK_ROOT / f"w{seq}-{case.case_id}"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(case.source_workspace_root or REPO_ROOT / "fixtures/v4/swebench_lite" / case.case_id, target)
    git = run_cmd(["git", "init", "-q"], cwd=str(target))
    if git.returncode != 0:
        log(f"git init failed: {git.stderr[:200]}")
        return None
    run_cmd(["git", "config", "user.email", "baseline@example.com"], cwd=str(target))
    run_cmd(["git", "config", "user.name", "baseline"], cwd=str(target))
    add = run_cmd(["git", "add", "-A"], cwd=str(target))
    if add.returncode != 0:
        log(f"git add failed: {add.stderr[:300]}")
        return None
    commit = run_cmd(["git", "commit", "-qm", "pristine"], cwd=str(target))
    if commit.returncode != 0:
        log(f"git commit failed: {commit.stderr[:300]}")
        return None
    return target


def extract_patch(workspace: Path) -> str:
    diff = run_cmd(["git", "diff", "HEAD"], cwd=str(workspace))
    return diff.stdout or ""


def verify(case, workspace: Path, timeout_s: int) -> tuple[bool, str]:
    proc, timed_out = run_with_timebox(
        [str(arg) for arg in case.verification_argv],
        timeout_s=timeout_s,
        cwd=str(workspace),
    )
    if timed_out:
        raise TimeoutExpired("verification", timeout_s)
    return proc.returncode == 0, (proc.stdout or "")[-2000:]


def run_case(args, case, seq: int) -> dict:
    record: dict = {
        "case_id": case.case_id,
        "model": args.model,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    workspace = prepare_workspace(case, seq)
    if workspace is None:
        record.update(verdict="workspace_error")
        return record
    prompt = (
        f"{case.query}\n\n"
        "Fix the issue in this repository with a minimal edit. "
        f"The verification command is: {' '.join(str(a) for a in case.verification_argv)}"
    )
    log(f"START {case.case_id} (opencode, timeout {args.timeout_min}min)")
    started = time.monotonic()
    try:
        proc, timed_out = run_with_timebox(
            [*opencode_prefix(), "run", "-m", args.model, "--dir", str(workspace), "--auto", prompt],
            timeout_s=args.timeout_min * 60,
            cwd=str(workspace),
            env=dict(os.environ, OPENROUTER_API_KEY=args.api_key),
        )
        record["opencode_exit"] = None if timed_out else proc.returncode
        record["timed_out"] = timed_out
        record["agent_output_tail"] = (proc.stdout or "")[-1500:]
    except OSError as exc:
        record["opencode_exit"] = None
        record["agent_output_tail"] = f"(spawn error: {exc})"
    record["duration_s"] = round(time.monotonic() - started, 1)

    patch = extract_patch(workspace)
    record["patch_lines"] = len(patch.splitlines())
    record["patch_head"] = patch[:800]
    if not patch.strip():
        record.update(verdict="no_patch")
    else:
        try:
            passed, tail = verify(case, workspace, args.verify_timeout_min * 60)
            record.update(verdict="resolved" if passed else "verification_failed", verify_tail=tail)
        except subprocess.TimeoutExpired:
            record.update(verdict="verification_timeout")
    record["finished_at"] = datetime.now().isoformat(timespec="seconds")
    log(
        f"EXIT {case.case_id} verdict={record['verdict']} "
        f"dur={record.get('duration_s')}s patch_lines={record.get('patch_lines')}"
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="openrouter/stealth/ox-alpha")
    parser.add_argument("--api-key", default=os.environ.get("OPENROUTER_API_KEY", ""))
    parser.add_argument("--fixtures-root", default=str(FIXTURES_ROOT_DEFAULT))
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--limit", type=int, help="first N corpus cases when no --case-id given")
    parser.add_argument("--timeout-min", type=float, default=20, help="opencode wall budget per case")
    parser.add_argument("--verify-timeout-min", type=float, default=15)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv)
    if not args.api_key:
        parser.error("OPENROUTER_API_KEY must be set or passed via --api-key")

    if args.probe:
        return 0 if probe(args.model, args.api_key) else 1

    case_ids: tuple[str, ...] | None = tuple(args.case_id) or None
    cases = swebench_lite_cases(Path(args.fixtures_root), case_ids)
    unfit = _load_gold_unfit_cases()
    skipped_unfit = [case.case_id for case in cases if case.case_id in unfit]
    if skipped_unfit:
        cases = [case for case in cases if case.case_id not in unfit]
        log(
            "skipping gold-unfit case(s) for fair pairing with the v4 lane: "
            + ", ".join(skipped_unfit)
        )
    if args.limit:
        cases = cases[: args.limit]
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    for seq, case in enumerate(cases, 1):
        record = run_case(args, case, seq)
        with LEDGER_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    log(f"DONE ({len(cases)} case(s)); ledger: {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
