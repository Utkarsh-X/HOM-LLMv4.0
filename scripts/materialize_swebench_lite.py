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
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


# Flask fixtures are src-layout checkouts: the package under test lives in
# ./src/ and plain pytest never puts it on sys.path, so `import flask`
# resolves to site-packages and verification measures the wrong Flask.
# Upstream's runner installs the workspace package first; restore that view.
# Shared alias-restoration conftest for sympy/requests/xarray fixtures.
_ALIAS_CONFTEST_SOURCE = '''import collections
import collections.abc

for _name in (
    "Mapping", "MutableMapping", "Sequence", "MutableSequence",
    "Set", "MutableSet", "Iterable", "Iterator", "Callable",
    "Hashable", "Sized", "Container", "Reversible",
):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))

try:
    import numpy as _np
except ImportError:
    pass
else:
    for _alias, _target in (
        ("unicode_", "str_"),
        ("string_", "bytes_"),
        ("bool8", "bool_"),
        ("float_", "float64"),
        ("complex_", "complex128"),
        ("object0", "object_"),
        ("int0", "int_"),
        ("uint0", "uint"),
    ):
        if not hasattr(_np, _alias) and hasattr(_np, _target):
            setattr(_np, _alias, getattr(_np, _target))
'''


_FLASK_CONFTEST_SOURCE = '''import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, 'src')
if os.path.isdir(_SRC):
    while _SRC in sys.path:
        sys.path.remove(_SRC)
    sys.path.insert(0, _SRC)
'''


# xarray-era (2019) code passes plain lists to pd.unique; modern pandas
# rejects them. Restore the historical dependency API surface — same spirit
# as the collections/numpy aliases — without touching any task content.
_XARRAY_CONFTEST_EXTRA_SOURCE = '''
try:
    import numpy as _np_compat
    import pandas as _pandas_compat

    _pandas_unique_real = _pandas_compat.unique

    def _pandas_unique_compat(values, *args, **kwargs):
        if isinstance(values, list):
            values = _np_compat.asarray(values)
        return _pandas_unique_real(values, *args, **kwargs)

    _pandas_compat.unique = _pandas_unique_compat
except ImportError:
    pass
'''


# Django fixtures get a root conftest restoring tests/runtests.py's
# environment: plain pytest otherwise skips both runtests.py settings
# injection and DiscoverRunner's pre-test database bootstrap.
_DJANGO_CONFTEST_SOURCE = '''import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, os.path.join(_ROOT, 'tests')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.test_sqlite')

import django
from django.conf import settings


def _apply_runtests_defaults(settings_obj):
    if getattr(settings_obj, 'INSTALLED_APPS', None):
        return
    settings_obj.INSTALLED_APPS = [
        'django.contrib.contenttypes',
        'django.contrib.auth',
        'django.contrib.sites',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.admin.apps.SimpleAdminConfig',
        'django.contrib.staticfiles',
    ]
    # runtests.py also registers the requested test packages themselves
    # (get_apps_to_install) so their models get an app_label. Plain pytest
    # never does, so derive them from the .py paths on the command line.
    # Args may be bare files or node ids (file.py::Class::test); both name
    # a path inside tests/, and verification runs use the node-id form.
    _tests_root = os.path.normpath(os.path.join(_ROOT, 'tests'))
    for _raw in sys.argv[1:]:
        _arg = _raw.strip()
        if _arg.startswith('-'):
            continue
        _path_arg = _arg.split('::', 1)[0]
        if not _path_arg.lower().endswith('.py'):
            continue
        _path = _path_arg if os.path.isabs(_path_arg) else os.path.normpath(
            os.path.join(os.getcwd(), _path_arg)
        )
        if not _path.startswith(_tests_root + os.sep):
            continue
        _parts = os.path.relpath(_path, _tests_root).split(os.sep)
        if len(_parts) >= 2 and _parts[0] not in settings_obj.INSTALLED_APPS:
            settings_obj.INSTALLED_APPS.append(_parts[0])
    settings_obj.MIDDLEWARE = [
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
    ]
    settings_obj.TEMPLATES = [{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(_ROOT, 'tests', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    }]
    settings_obj.ROOT_URLCONF = 'urls'
    settings_obj.STATIC_URL = 'static/'
    settings_obj.LANGUAGE_CODE = 'en'
    settings_obj.SITE_ID = 1
    settings_obj.MIGRATION_MODULES = {
        'auth': None,
        'contenttypes': None,
        'sessions': None,
    }


try:
    _apply_runtests_defaults(settings)
    django.setup()
except Exception:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'test_sqlite'
    django.setup()


# Canonical runners build their test databases BEFORE any test executes
# (DiscoverRunner.run_tests -> setup_databases): Django's own test_sqlite
# settings deliberately omit DATABASES NAME, and connections are expected to
# point at populated in-memory test databases created up front. Plain pytest
# skips that step, so DB-backed TestCase.setUpClass dies with
# ImproperlyConfigured ("Please supply the NAME value") regardless of the code
# under test -- an environment gap, not a task result. Restore the canonical
# order here: create the in-memory test databases (migrations + run_syncdb)
# once at conftest import, exactly as runtests.py would have done by then.
try:
    import contextlib
    import inspect

    from django.test.utils import setup_databases, setup_test_environment

    setup_test_environment()
    # The signature drifted across Django versions: checkouts from late 2020
    # demand a keyword-only ``time_keeper`` wrapping database-creation steps
    # that older/newer releases do not accept (or default). Pass exactly what
    # this checkout's signature requires.
    _params = inspect.signature(setup_databases).parameters
    _kwargs = {'verbosity': 0, 'interactive': False}
    if 'time_keeper' in _params and _params['time_keeper'].default is inspect.Parameter.empty:
        class _NullTimeKeeper:
            def timed(self, label):
                return contextlib.nullcontext()

        _kwargs['time_keeper'] = _NullTimeKeeper()
    setup_databases(**_kwargs)
except Exception:
    # Non-database suites must keep working if database bootstrapping is
    # impossible here; affected tests will surface the original error
    # themselves at setup, and the traceback stays visible in stderr.
    import traceback

    print(
        "[fixture-conftest] test database bootstrap failed:",
        file=sys.stderr,
    )
    traceback.print_exc()
'''


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

    Handles three entry shapes seen in the dataset:
    - already-resolved ids (contain ``::`` or ``/``): passed through;
    - unittest-style verbose ids ``test_x (pkg.mod.ClassName)``: mapped to
      ``<file-for-module>::ClassName::test_x``;
    - bare names ``test_x``: joined with every test file touched by the
      hidden patch. Non-identifier names (unittest picks up method
      docstrings as test titles) cannot form node ids, so fall back to the
      whole file — running the file is a strictly stronger check.
    """
    resolved: list[str] = []
    seen: set[str] = set()
    for name in f2p:
        candidates: list[str] = []
        if "::" in name or "/" in name:
            candidates.append(name)
        else:
            verbose = _VERBOSE_TEST_NAME_RE.match(name.strip())
            if verbose:
                test_name, dotted = verbose.group(1), verbose.group(2)
                node = _verbose_to_node_id(test_name, dotted, test_files)
                if node:
                    candidates.append(node)
            elif name.isidentifier():
                candidates.extend(f"{tf}::{name}" for tf in test_files)
            else:
                candidates.extend(test_files)
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                resolved.append(candidate)
    return tuple(resolved)


_VERBOSE_TEST_NAME_RE = re.compile(r"^(\S+)\s+\(([\w.]+)\)$")


def _verbose_to_node_id(test_name: str, dotted: str, test_files: tuple[str, ...]) -> str | None:
    parts = dotted.split(".")
    # Longest suffix of the dotted path matching a patched test file wins;
    # the remaining leading components are the class chain.
    for split in range(len(parts)):
        module = ".".join(parts[: len(parts) - split]) if split else dotted
        classes = list(parts[len(parts) - split :]) if split else []
        candidate_suffix = module.replace(".", "/") + ".py"
        matches = [tf for tf in test_files if tf.endswith(candidate_suffix)]
        if matches:
            # unittest sometimes repeats the method name (or its docstring
            # title) as the last "class" component; drop those echoes.
            while classes and classes[-1] == test_name:
                classes.pop()
            node = matches[0]
            for cls in classes:
                node = f"{node}::{cls}"
            return f"{node}::{test_name}"
    return None


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
    # Collect by FILE, never by node id: when any node-id argument fails to
    # resolve, pytest exits non-zero and prints no id list at all, masking
    # the ids that do collect. File arguments always resolve, and each
    # resolved node id is then matched against the collected descendants.
    files: list[str] = []
    seen_files: set[str] = set()
    for node in node_ids:
        path = node.split("::", 1)[0]
        if path not in seen_files:
            seen_files.add(path)
            files.append(path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--rootdir=.", *files],
        cwd=work_root,
        capture_output=True,
        text=True,
        timeout=600,
    )
    stdout_lines = set(proc.stdout.splitlines())
    collected: list[str] = []
    for node in node_ids:
        # Collected lines carry parametrization suffixes, so compare the
        # pre-'[' prefix; file-level ids match their collected descendants.
        key = node.split("[", 1)[0].replace("\\", "/")
        for line in stdout_lines:
            base = line.split("[", 1)[0].replace("\\", "/")
            if base == key or base.startswith(key + "::"):
                collected.append(node)
                break
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

    # Repo-specific collection shims: our harness runs plain pytest inside the
    # copied workspace, while some projects' own test suites expect their
    # canonical runner's environment setup. The shim only restores that
    # environment (paths/settings); it never touches task content or tests.
    if repo in ("sympy/sympy", "psf/requests", "pydata/xarray"):
        # Historical commits import the ABCs from ``collections`` and use
        # NumPy aliases that NumPy 2 removed; _ALIAS_CONFTEST_SOURCE
        # restores that view. xarray additionally gets the pandas-compat
        # block appended.
        conftest_source = _ALIAS_CONFTEST_SOURCE
        if repo == "pydata/xarray":
            conftest_source += _XARRAY_CONFTEST_EXTRA_SOURCE
        (fixture_dir / "conftest.py").write_text(
            conftest_source, encoding="utf-8"
        )
    if repo == "django/django":
        # Django's own suite expects the environment tests/runtests.py builds;
        # _DJANGO_CONFTEST_SOURCE restores it (settings defaults derived from
        # argv, then DiscoverRunner-style in-memory test database creation).
        (fixture_dir / "conftest.py").write_text(
            _DJANGO_CONFTEST_SOURCE, encoding="utf-8"
        )
    if repo == "pallets/flask":
        (fixture_dir / "conftest.py").write_text(
            _FLASK_CONFTEST_SOURCE, encoding="utf-8"
        )

    valid_ids = _collect_node_ids(fixture_dir, node_ids)
    if not valid_ids:
        raise SystemExit(
            f"{instance_id}: none of the FAIL_TO_PASS node ids collect "
            f"(resolved {node_ids!r} from files {test_files!r})"
        )
    p2p = _parse_test_list(row.get("PASS_TO_PASS"))
    p2p_node_ids = _resolve_node_ids(p2p, test_files)
    valid_p2p = _collect_node_ids(fixture_dir, p2p_node_ids)

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
        "pass_to_pass": list(p2p),
        "pass_to_pass_node_ids": list(valid_p2p),
        "target_files": target_files,
    }
    (fixture_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return fixture_dir


def _validate_gold_fixture(fixture_dir: Path) -> tuple[bool, str]:
    """Apply the manifest gold patch and require FAIL_TO_PASS to pass.

    Baseline-only validation cannot distinguish a genuine pre-fix failure from
    an environment error at setup: both make FAIL_TO_PASS fail before the patch.
    A poisoned fixture like that scores real proposals as verification_failed
    (django-14017 did exactly that against a byte-exact gold patch). Requiring
    the gold patch itself to turn FAIL_TO_PASS green closes the gap. Every file
    the patch touches is restored byte-exact afterwards.
    """
    import contextlib

    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    gold_patch = manifest.get("patch") or ""
    f2p_ids = list(manifest.get("fail_to_pass") or [])
    if not gold_patch or not f2p_ids:
        return False, "manifest lacks gold patch or fail_to_pass ids"

    touched = [
        line.split(" b/", 1)[-1]
        for line in gold_patch.splitlines()
        if line.startswith("diff --git")
    ]
    if not touched:
        return False, "gold patch declares no files"

    repo_root = Path(__file__).resolve().parents[1]
    rel_dir = fixture_dir.resolve().relative_to(repo_root)
    log_dir = repo_root / "temp/mvp/campaign/gold_validation_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def _note(message: str) -> None:
        print(
            f"[gold-validate {fixture_dir.name} +{time.monotonic() - started:.1f}s] {message}",
            flush=True,
        )

    # Back up pre-patch state so the fixture returns pristine even on failure.
    # Patch-header paths are fixture-relative; resolve them against the
    # fixture's own directory inside the repo worktree.
    backups: dict[str, bytes | None] = {}
    targets: dict[str, Path] = {}
    for rel in touched:
        target = repo_root / rel_dir / rel
        targets[rel] = target
        backups[rel] = target.read_bytes() if target.exists() else None

    def _restore() -> None:
        for rel, data in backups.items():
            target = targets[rel]
            if data is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_bytes(data)

    def _restored_exactly() -> bool:
        return all(
            (targets[rel].exists() == (backups[rel] is not None))
            and (
                backups[rel] is None
                or targets[rel].read_bytes() == backups[rel]
            )
            for rel in backups
        )

    try:
        patch_file = fixture_dir / "_gold_validation.patch"
        patch_file.write_text(gold_patch, encoding="utf-8")
        try:
            applied = subprocess.run(
                ["git", "apply", f"--directory={rel_dir.as_posix()}", str(patch_file)],
                cwd=str(repo_root), capture_output=True, text=True,
            )
            if applied.returncode != 0:
                return False, f"gold patch does not apply: {applied.stderr.strip()[:200]}"
        finally:
            with contextlib.suppress(OSError):
                patch_file.unlink()
        _note("gold applied")

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", *f2p_ids],
            cwd=str(fixture_dir), capture_output=True, text=True, timeout=1800,
        )
        tail = next(
            (l for l in reversed(proc.stdout.splitlines()) if l.strip()),
            "",
        )
        _note(f"pytest exit={proc.returncode}")
        (log_dir / f"{fixture_dir.name}.log").write_text(
            proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""),
            encoding="utf-8",
        )
    finally:
        _restore()
        if not _restored_exactly():
            # One retry: transient Windows sharing violations are the usual
            # suspect; never leave a fixture silently un-restored.
            time.sleep(2)
            _restore()
            if not _restored_exactly():
                _note("RESTORE FAILED twice -- fixture left modified")
                return True, (
                    "restoration FAILED -- fixture left modified; inspect before use"
                )

    verdict = "green" if proc.returncode == 0 else "not green"
    suffix = "" if _restored_exactly() else " (restoration unverified)"
    if proc.returncode != 0:
        return False, f"FAIL_TO_PASS {verdict} under gold patch ({tail.strip()[:120]}){suffix}"
    return True, f"gold patch turns FAIL_TO_PASS {verdict} ({tail.strip()[:120]}){suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--checkout-root", required=True, type=Path)
    parser.add_argument("--instance-id", action="append")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="corpus manifest JSON ({\"tasks\": [{\"instance_id\": ...}, ...]}) "
        "instead of repeated --instance-id flags",
    )
    parser.add_argument(
        "--tolerant",
        action="store_true",
        help="keep going when a single task fails to materialize; report at the end",
    )
    parser.add_argument(
        "--validate-gold",
        action="append",
        metavar="INSTANCE_ID",
        help="skip materialization; apply the existing fixture's gold patch and "
        "require FAIL_TO_PASS to pass, then restore the fixture (repeatable)",
    )
    args = parser.parse_args(argv)
    args.fixtures_root = args.fixtures_root.resolve()
    args.checkout_root = args.checkout_root.resolve()

    if args.validate_gold:
        failures: dict[str, str] = {}
        for instance_id in args.validate_gold:
            fixture_dir = args.fixtures_root / instance_id
            if not (fixture_dir / "manifest.json").exists():
                failures[instance_id] = "no materialized fixture with a manifest"
                continue
            ok, detail = _validate_gold_fixture(fixture_dir)
            print(f"{'PASS' if ok else 'FAIL'} gold-validation {instance_id}: {detail}", flush=True)
            if not ok:
                failures[instance_id] = detail
        print(f"gold validation done: {len(args.validate_gold) - len(failures)} passed, {len(failures)} failed")
        if failures:
            print(json.dumps({"failed": dict(sorted(failures.items()))}, indent=2))
            return 1
        return 0

    requested: list[str] = list(args.instance_id or [])
    if args.manifest is not None:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        for task in manifest.get("tasks", []):
            requested.append(str(task["instance_id"]))
    if not requested:
        parser.error("no tasks requested: pass --instance-id and/or --manifest")

    rows = _selected(tuple(requested))
    fixtures_root = args.fixtures_root
    fixtures_root.mkdir(parents=True, exist_ok=True)
    failed: dict[str, str] = {}
    for row in rows:
        try:
            fixture_dir = _materialize_one(row, fixtures_root, args.checkout_root)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported and counted below
            if not args.tolerant:
                raise
            failed[str(row["instance_id"])] = f"{type(exc).__name__}: {exc}"
            print(f"FAILED {row['instance_id']}: {type(exc).__name__}: {exc}", flush=True)
            continue
        print(f"materialized {row['instance_id']} -> {fixture_dir}", flush=True)
    print(f"done: {len(rows) - len(failed)} materialized, {len(failed)} failed")
    if failed:
        print(json.dumps({"failed": dict(sorted(failed.items()))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
