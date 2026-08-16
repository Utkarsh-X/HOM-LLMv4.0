"""Materialize SWE-bench Lite task fixtures for the v4 benchmark.

For each selected task, this:
1. Reads the task metadata from the SWE-bench Lite dataset (issue text,
   base commit, gold patch, test patch, FAIL_TO_PASS / PASS_TO_PASS tests).
2. Checks out the repository at ``base_commit`` into a shared checkout dir.
3. Applies the ``test_patch`` (the hidden tests the agent never sees) with
   ``git apply`` *inside the checkout* -- git apply silently skips patches
   when run outside a git work tree (observed on Windows).
4. Copies the working tree (minus ``.git``) into
   ``<fixtures_root>/<instance_id>/``.
5. Resolves FAIL_TO_PASS entries to full pytest node ids against the test
   files touched by ``test_patch``, and validates they collect.
6. Writes ``manifest.json`` with the task metadata the benchmark runner needs.

The gold ``patch`` is NOT applied - the fixture is left buggy (FAIL_TO_PASS).

Usage:
    python scripts/materialize_swebench_lite.py \
      --fixtures-root fixtures/v4/swebench_lite \
      --checkout-root temp/swe_checkouts \
      --instance-id sympy__sympy-21627 [--instance-id ...]

Requires network access for the dataset + git clones (one-time).
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _task_rows() -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return list(ds)


def _selected(instance_ids: tuple[str, ...]) -> list[dict]:
    rows = _task_rows()
    by_id = {row["instance_id"]: row for row in rows}
    missing = [iid for iid in instance_ids if iid not in by_id]
    if missing:
        raise SystemExit(f"unknown instance_ids: {missing}")
    return [by_id[iid] for iid in instance_ids]


def _parse_test_list(raw) -> tuple[str, ...]:
    if isinstance(raw, list):
        return tuple(str(x) for x in raw)
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        value = []
    if not isinstance(value, list):
        value = []
    return tuple(str(x) for x in value)


def _repo_dir(checkout_root: Path, repo: str) -> Path:
    """Return the shared checkout dir for a repo (cloned lazily)."""
    return checkout_root / repo.replace("/", "__")


def _ensure_checkout(repo: str, base_commit: str, checkout_root: Path) -> Path:
    target = _repo_dir(checkout_root, repo)
    if not (target / ".git").exists():
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--filter=blob:none",
                f"https://github.com/{repo}.git",
                str(target),
            ],
            check=True,
            timeout=900,
        )
    # Force-clean the working tree to the task's base commit (discards any
    # test/gold patches a previous task left applied).
    subprocess.run(
        ["git", "-C", str(target), "checkout", "--quiet", "--force", base_commit],
        check=True,
        timeout=120,
    )
    return target


def _test_files_from_patch(patch: str) -> tuple[str, ...]:
    files: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git") and " b/" in line:
            path = line.split(" b/", 1)[-1]
            if "test" in path:
                files.append(path)
    return tuple(files)


def _resolve_node_ids(f2p: tuple[str, ...], test_files: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve bare SWE-bench test names to full pytest node ids.

    SWE-bench Lite FAIL_TO_PASS entries are usually bare names (e.g.
    ``test_Abs``) that must be joined with the test file the patch touches
    (``sympy/.../test_complexes.py::test_Abs``). Entries that already carry a
    path or ``::`` are passed through unchanged.
    """
    resolved: list[str] = []
    for name in f2p:
        if "::" in name or "/" in name:
            resolved.append(name)
        else:
            for tf in test_files:
                resolved.append(f"{tf}::{name}")
    return tuple(resolved)


def _applies_cleanly(checkout: Path, patch: str) -> None:
    if not patch:
        return
    patch_file = checkout / ".task_test_patch.diff"
    patch_file.write_text(patch, encoding="utf-8", newline="\n")
    try:
        subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch_file.resolve())],
            cwd=str(checkout.resolve()),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"test_patch failed to apply for {checkout.name}:\n"
            f"{exc.stderr}"
        ) from exc
    finally:
        patch_file.unlink(missing_ok=True)


def _collect_node_ids(work_root: Path, node_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Return only node ids pytest can actually collect (validates resolution)."""
    if not node_ids:
        return ()
    collected: list[str] = []
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *node_ids],
        cwd=work_root,
        capture_output=True,
        text=True,
        timeout=600,
    )
    stdout_lines = set(proc.stdout.splitlines())
    for node in node_ids:
        # A collected node id appears in --collect-only -q output (possibly
        # with parametrization suffixes, so match by prefix before '[').
        key = node.split("[", 1)[0]
        if any(ln.startswith(key) for ln in stdout_lines):
            collected.append(node)
    return tuple(collected)


def _materialize_one(row: dict, fixtures_root: Path, checkout_root: Path) -> Path:
    instance_id = str(row["instance_id"])
    repo = str(row["repo"])
    base_commit = str(row["base_commit"])
    fixture_dir = fixtures_root / instance_id
    if fixture_dir.exists():
        shutil.rmtree(fixture_dir)

    checkout = _ensure_checkout(repo, base_commit, checkout_root)
    test_patch = row.get("test_patch") or ""
    _applies_cleanly(checkout, test_patch)

    # Copy the working tree (with the hidden tests applied) into the fixture,
    # excluding .git. copytree never touches the checkout's .git, so no
    # Windows read-only pack-file locks.
    fixture_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        checkout,
        fixture_dir,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
        dirs_exist_ok=True,
    )

    test_files = _test_files_from_patch(test_patch)
    f2p = _parse_test_list(row.get("FAIL_TO_PASS"))
    node_ids = _resolve_node_ids(f2p, test_files)
    valid_ids = _collect_node_ids(fixture_dir, node_ids)
    if not valid_ids:
        raise SystemExit(
            f"{instance_id}: none of the FAIL_TO_PASS node ids collect "
            f"(resolved {node_ids!r} from files {test_files!r})"
        )

    target_files = tuple(
        line.split(" b/", 1)[-1]
        for line in (row.get("patch") or "").splitlines()
        if line.startswith("diff --git")
    )
    manifest = {
        "instance_id": instance_id,
        "repo": repo,
        "base_commit": base_commit,
        "problem_statement": row.get("problem_statement") or "",
        "patch": row.get("patch") or "",
        "test_patch": test_patch,
        "fail_to_pass": list(valid_ids),
        "fail_to_pass_raw": list(f2p),
        "pass_to_pass": list(_parse_test_list(row.get("PASS_TO_PASS"))),
        "target_files": target_files,
    }
    (fixture_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return fixture_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--checkout-root", required=True, type=Path)
    parser.add_argument("--instance-id", action="append", required=True)
    args = parser.parse_args(argv)
    args.fixtures_root = args.fixtures_root.resolve()
    args.checkout_root = args.checkout_root.resolve()

    rows = _selected(tuple(args.instance_id))
    fixtures_root = args.fixtures_root
    fixtures_root.mkdir(parents=True, exist_ok=True)
    for row in rows:
        fixture_dir = _materialize_one(row, fixtures_root, args.checkout_root)
        print(f"materialized {row['instance_id']} -> {fixture_dir}")
    print(f"done: {len(rows)} fixtures under {fixtures_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
