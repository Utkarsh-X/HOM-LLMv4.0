"""Select a curated SWE-bench Lite evaluation corpus.

Builds ``configs/v4/swebench_corpus_v1.json``: a fixed, deterministic,
actively-selected task list used to benchmark the v4 harness.

Selection rules (v1):
1. Repo scope restricted to pure-Python-importable projects -- our harness
   verifies by running plain pytest inside the copied workspace with the
   system venv, so projects needing compiled extensions at import time
   (matplotlib, astropy, scikit-learn) cannot verify here and are excluded.
2. Domain quotas favor coverage breadth without over-thinning any domain:
   django 55 (web/backend logic), sympy 30 (symbolic math),
   sphinx 6 (docs tooling), xarray 3 / flask 3 / requests 3 (API/data probes).
3. Difficulty stratification inside each major repo by gold-patch size
   (small <=10 changed lines, medium 11-40, large >40) targeting an
   approximately 50/30/20 small/medium/large split.
4. Deterministic: candidates sorted per (repo, bucket), sampled with
   random.Random(20260824); the manifest records everything needed to audit
   or reproduce the exact task set.
5. Spare tasks (lowest priority within over-quota repos) cover fixtures that
   fail to materialize so the final corpus still reaches 100 verified tasks.

Usage:
    python scripts/select_swebench_corpus.py \
      [--output configs/v4/swebench_corpus_v1.json]
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SAMPLE_SEED = 20260824

# repo -> (primary_quota, spares)
REPO_QUOTAS = {
    "django/django": (55, 7),
    "sympy/sympy": (30, 5),
    "sphinx-doc/sphinx": (6, 0),
    "pydata/xarray": (3, 0),
    "pallets/flask": (3, 0),
    "psf/requests": (3, 0),
}

# Target proportions of small/medium/large within each repo's primary quota.
BUCKET_SPLIT = {"S": 0.5, "M": 0.3, "L": 0.2}


def _patch_line_count(patch: str) -> int:
    return sum(
        1
        for line in (patch or "").splitlines()
        if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    )


def _bucket(patch_lines: int) -> str:
    if patch_lines <= 10:
        return "S"
    if patch_lines <= 40:
        return "M"
        # unreachable; kept for clarity
    return "L"


def _task_rows() -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return [dict(row) for row in ds]


def select() -> dict:
    rows = _task_rows()
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        repo = str(row["repo"])
        if repo not in REPO_QUOTAS:
            continue
        patch_lines = _patch_line_count(str(row.get("patch") or ""))
        f2p_raw = row.get("FAIL_TO_PASS")
        try:
            f2p_count = len(json.loads(f2p_raw)) if isinstance(f2p_raw, str) else len(f2p_raw or [])
        except (TypeError, ValueError, json.JSONDecodeError):
            f2p_count = 0
        enriched = dict(row)
        enriched["patch_lines"] = patch_lines
        enriched["fail_to_pass_count"] = f2p_count
        enriched["bucket"] = _bucket(patch_lines)
        by_repo[repo].append(enriched)

    rng = random.Random(SAMPLE_SEED)
    tasks: list[dict] = []
    for repo, (quota, spares) in REPO_QUOTAS.items():
        pool = by_repo.get(repo, [])
        grouped: dict[str, list[dict]] = defaultdict(list)
        for candidate in pool:
            grouped[candidate["bucket"]].append(candidate)
        for bucket in grouped:
            grouped[bucket].sort(key=lambda r: str(r["instance_id"]))
            rng.shuffle(grouped[bucket])

        picks: list[tuple[str, dict]] = []
        remaining = quota
        for bucket in ("S", "M", "L"):
            want = round(quota * BUCKET_SPLIT[bucket])
            take = grouped[bucket][:want]
            picks.extend((bucket, item) for item in take)
            del grouped[bucket][:want]
            remaining -= len(take)
        leftovers = grouped["S"] + grouped["M"] + grouped["L"]
        picks.extend((leftover["bucket"], leftover) for leftover in leftovers[:remaining])

        seen = {str(item["instance_id"]) for _, item in picks}
        spare_picks: list[tuple[str, dict]] = []
        for bucket in ("S", "M", "L"):
            for candidate in grouped[bucket]:
                iid = str(candidate["instance_id"])
                if iid not in seen and len(spare_picks) < spares:
                    spare_picks.append((bucket, candidate))
                    seen.add(iid)

        for offset, (is_spare, entry) in enumerate(
            [(False, p) for p in picks] + [(True, s) for s in spare_picks]
        ):
            _, item = entry
            tasks.append(
                {
                    "instance_id": str(item["instance_id"]),
                    "repo": repo,
                    "difficulty_bucket": item["bucket"],
                    "patch_lines": item["patch_lines"],
                    "fail_to_pass_count": item["fail_to_pass_count"],
                    "spare": is_spare,
                    "priority": offset,
                }
            )

    repo_counts = Counter(t["repo"] for t in tasks if not t["spare"])
    bucket_counts = Counter(t["difficulty_bucket"] for t in tasks if not t["spare"])
    manifest = {
        "version": "v1",
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "sample_seed": SAMPLE_SEED,
        "selection_rules": {
            "repo_scope": "pure-python-importable projects only",
            "quotas_primary": {r: q for r, (q, _) in REPO_QUOTAS.items()},
            "difficulty_split_target": BUCKET_SPLIT,
            "excluded_repos_compiled": [
                "matplotlib/matplotlib",
                "astropy/astropy",
                "scikit-learn/scikit-learn",
                "mwaskom/seaborn",
            ],
        },
        "summary": {
            "total_tasks": sum(1 for t in tasks if not t["spare"]),
            "spare_tasks": sum(1 for t in tasks if t["spare"]),
            "per_repo": dict(sorted(repo_counts.items())),
            "per_bucket": dict(sorted(bucket_counts.items())),
        },
        "tasks": tasks,
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("configs/v4/swebench_corpus_v1.json"))
    args = parser.parse_args(argv)

    manifest = select()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["summary"], indent=2))
    print(f"corpus written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
