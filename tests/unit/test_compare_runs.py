"""Tests for eval.compare_runs."""

from __future__ import annotations

import json
from pathlib import Path

from eval import compare_runs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_summarize_reads_nested_judge_scores_and_verdict_flips(tmp_path: Path):
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()

    _write_jsonl(
        run_a / "judge_results__gemini.jsonl",
        [
            {
                "query_id": 9,
                "verdict": "improved",
                "scores": {
                    "overall_quality": {"candidate": 5, "baseline": 4},
                    "completeness": {"candidate": 5, "baseline": 4},
                },
            }
        ],
    )
    _write_jsonl(
        run_b / "judge_results__gemini.jsonl",
        [
            {
                "query_id": 9,
                "verdict": "regressed",
                "scores": {
                    "overall_quality": {"candidate": 4, "baseline": 5},
                    "completeness": {"candidate": 4, "baseline": 5},
                },
            }
        ],
    )

    rows, aggregate = compare_runs.summarize_run_dirs(run_a, run_b)

    assert aggregate == -1.0
    assert rows == [
        {
            "query_id": 9,
            "a_overall": 5.0,
            "b_overall": 4.0,
            "delta": -1.0,
            "verdict_a": "improved",
            "verdict_b": "regressed",
            "answer_chars_a": None,
            "answer_chars_b": None,
            "answer_chars_delta": None,
            "tokens_out_a": None,
            "tokens_out_b": None,
            "tokens_out_delta": None,
            "bm25_count_a": None,
            "bm25_count_b": None,
            "vector_count_a": None,
            "vector_count_b": None,
            "context_blocks_a": None,
            "context_blocks_b": None,
            "retrieval_disagreement_a": None,
            "retrieval_disagreement_b": None,
            "top_file_concentration_a": None,
            "top_file_concentration_b": None,
        }
    ]


def test_summarize_includes_response_and_telemetry_deltas(tmp_path: Path):
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()
    telemetry_a = tmp_path / "telemetry_a.json"
    telemetry_b = tmp_path / "telemetry_b.json"
    telemetry_a.write_text(
        json.dumps(
            {
                "phases": {
                    "RETRIEVAL": {"bm25_count": 60, "vector_count": 0},
                    "CONTEXT": {
                        "blocks": 25,
                        "context_synthesis": {"retrieval_disagreement": 0.0},
                        "depth_preservation_check": {"top_file_concentration_ratio": 0.2},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    telemetry_b.write_text(
        json.dumps(
            {
                "phases": {
                    "RETRIEVAL": {"bm25_count": 70, "vector_count": 70},
                    "CONTEXT": {
                        "blocks": 31,
                        "context_synthesis": {"retrieval_disagreement": 1.0},
                        "depth_preservation_check": {"top_file_concentration_ratio": 0.16129},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    for run, verdict, overall in ((run_a, "improved", 5), (run_b, "regressed", 4)):
        _write_jsonl(
            run / "judge_results__gemini.jsonl",
            [
                {
                    "query_id": 9,
                    "verdict": verdict,
                    "scores": {"overall_quality": {"candidate": overall, "baseline": 5}},
                }
            ],
        )
    _write_jsonl(
        run_a / "responses.jsonl",
        [{"query_id": 9, "answer_text": "abc", "tokens_out": 10, "telemetry_path": str(telemetry_a)}],
    )
    _write_jsonl(
        run_b / "responses.jsonl",
        [{"query_id": 9, "answer_text": "abcdef", "tokens_out": 12, "telemetry_path": str(telemetry_b)}],
    )

    rows, _ = compare_runs.summarize_run_dirs(run_a, run_b)

    row = rows[0]
    assert row["answer_chars_delta"] == 3
    assert row["tokens_out_delta"] == 2
    assert row["vector_count_a"] == 0
    assert row["vector_count_b"] == 70
    assert row["retrieval_disagreement_a"] == 0.0
    assert row["retrieval_disagreement_b"] == 1.0
