#!/usr/bin/env python3
"""Orchestrate config variant generation, experiment runs, and repeated judging."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVAL_EXPERIMENT = ROOT / "eval" / "run_experiment.py"
EVAL_JUDGE = ROOT / "eval" / "run_judge.py"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping root in {path}")
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def _safe_name(value: str) -> str:
    cleaned = []
    for char in value:
        if char.isalnum() or char in {"_", "-", "."}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    token = "".join(cleaned).strip("._-")
    return token or "unnamed"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _run_command(cmd: list[str], cwd: Path) -> None:
    rendered = " ".join(f'"{part}"' if " " in part else part for part in cmd)
    print(f"[RUN] {rendered}")
    subprocess.run(cmd, cwd=cwd, check=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _verdict_map(path: Path) -> dict[int, str]:
    return {
        int(row["query_id"]): str(row.get("verdict", "")).strip().lower()
        for row in _read_jsonl(path)
    }


def _judge_outputs_disagree(paths: list[Path]) -> bool:
    if len(paths) < 2:
        return False
    maps = [_verdict_map(path) for path in paths]
    reference = maps[0]
    all_ids = set(reference)
    for item in maps[1:]:
        all_ids.update(item)
    for item in maps[1:]:
        for query_id in all_ids:
            if reference.get(query_id) != item.get(query_id):
                return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a tuning batch from a manifest.")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to tuning manifest YAML.")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if a single experiment or judge pass fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = (ROOT / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    manifest = _load_yaml(manifest_path)

    batch_name = _safe_name(str(manifest.get("batch_name", manifest_path.stem)))
    base_config_path = manifest.get("base_config")
    if not base_config_path:
        raise ValueError("Manifest must define base_config")
    base_config_path = (ROOT / Path(base_config_path)).resolve()
    base_config = _load_yaml(base_config_path)

    generated_root = (ROOT / Path(manifest.get("config_output_dir", "tuning/generated_configs")) / batch_name).resolve()
    results_root = (ROOT / Path(manifest.get("results_output_dir", "tuning/results")) / batch_name).resolve()
    generated_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)

    eval_cfg = manifest.get("eval", {})
    judge_cfg = manifest.get("judge", {})
    experiments = manifest.get("experiments", [])
    if not experiments:
        raise ValueError("Manifest must define at least one experiment")

    generation_targets = eval_cfg.get("generation_targets") or [{"name": "default"}]
    generation_repeats = max(1, int(eval_cfg.get("generation_repeats", 1)))
    judge_targets = judge_cfg.get("judge_targets") or [{"name": "default"}]
    judge_repeats = max(1, int(judge_cfg.get("repeats", 2)))
    extra_repeat_on_disagreement = bool(judge_cfg.get("extra_repeat_on_any_query_disagreement", False))

    batch_record: dict[str, Any] = {
        "batch_name": batch_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "base_config_path": str(base_config_path),
        "generated_root": str(generated_root),
        "results_root": str(results_root),
        "experiments": [],
    }

    baseline_path = (ROOT / Path(judge_cfg["baseline"])).resolve()
    judge_config_path = (ROOT / Path(judge_cfg["judge_config"])).resolve()

    for experiment in experiments:
        experiment_name = _safe_name(str(experiment["name"]))
        overrides = experiment.get("overrides", {})
        config_payload = _deep_merge(base_config, overrides)
        config_path = generated_root / f"{experiment_name}.yaml"
        _write_yaml(config_path, config_payload)

        experiment_record: dict[str, Any] = {
            "name": experiment_name,
            "group": experiment.get("group"),
            "rationale": experiment.get("rationale"),
            "config_path": str(config_path),
            "overrides": overrides,
            "generation_runs": [],
        }

        for generation_target in generation_targets:
            gen_name = _safe_name(str(generation_target.get("name", "default")))
            provider = generation_target.get("provider")
            model = generation_target.get("model")

            for generation_index in range(1, generation_repeats + 1):
                run_name = f"{batch_name}__{experiment_name}__{gen_name}__g{generation_index}"
                cmd = [
                    sys.executable,
                    str(EVAL_EXPERIMENT),
                    "--select",
                    str(eval_cfg.get("select", "1-20")),
                    "--config",
                    str(config_path),
                    "--run-name",
                    run_name,
                ]
                if provider:
                    cmd.extend(["--provider", str(provider)])
                if model:
                    cmd.extend(["--model", str(model)])

                try:
                    _run_command(cmd, ROOT)
                except subprocess.CalledProcessError:
                    if args.stop_on_error:
                        raise
                    continue

                responses_path = ROOT / "eval" / "runs" / run_name / "responses.jsonl"
                if not responses_path.exists():
                    raise FileNotFoundError(f"Expected responses file not found: {responses_path}")

                generation_record: dict[str, Any] = {
                    "generation_target": gen_name,
                    "generation_index": generation_index,
                    "run_name": run_name,
                    "provider": provider,
                    "model": model,
                    "responses_path": str(responses_path),
                    "judge_runs": [],
                }

                for judge_target in judge_targets:
                    judge_name = _safe_name(str(judge_target.get("name", "default")))
                    judge_provider = judge_target.get("provider")
                    judge_dir = results_root / experiment_name / gen_name / f"g{generation_index}" / judge_name
                    judge_dir.mkdir(parents=True, exist_ok=True)

                    judge_output_paths: list[Path] = []
                    planned_passes = judge_repeats
                    pass_index = 1
                    while pass_index <= planned_passes:
                        judge_output = judge_dir / f"judge_results__pass{pass_index}.jsonl"
                        cmd = [
                            sys.executable,
                            str(EVAL_JUDGE),
                            "--responses",
                            str(responses_path),
                            "--baseline",
                            str(baseline_path),
                            "--judge-config",
                            str(judge_config_path),
                            "--output",
                            str(judge_output),
                        ]
                        if judge_provider:
                            cmd.extend(["--provider", str(judge_provider)])

                        try:
                            _run_command(cmd, ROOT)
                        except subprocess.CalledProcessError:
                            if args.stop_on_error:
                                raise
                            break

                        judge_output_paths.append(judge_output)
                        generation_record["judge_runs"].append(
                            {
                                "judge_target": judge_name,
                                "judge_provider": judge_provider,
                                "pass_index": pass_index,
                                "output_path": str(judge_output),
                            }
                        )

                        if (
                            pass_index == judge_repeats
                            and extra_repeat_on_disagreement
                            and judge_repeats >= 2
                            and _judge_outputs_disagree(judge_output_paths)
                        ):
                            planned_passes = judge_repeats + 1

                        pass_index += 1

                experiment_record["generation_runs"].append(generation_record)

        batch_record["experiments"].append(experiment_record)
        batch_manifest_path = results_root / "batch_manifest.json"
        batch_manifest_path.write_text(json.dumps(batch_record, indent=2), encoding="utf-8")

    final_manifest_path = results_root / "batch_manifest.json"
    final_manifest_path.write_text(json.dumps(batch_record, indent=2), encoding="utf-8")
    print(f"Batch manifest written to: {final_manifest_path}")


if __name__ == "__main__":
    main()
