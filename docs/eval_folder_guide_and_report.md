# HOM-LLM Evaluation Framework: Complete Guide & Analysis Report

> **Version**: 2.0  
> **Generated**: 2026-01-21  
> **Status**: Implementation Analysis Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Folder Structure](#folder-structure)
3. [File Analysis & Implementation Review](#file-analysis--implementation-review)
   - [3.1 queries.json](#31-queriesjson)
   - [3.2 cursor_baseline.json](#32-cursor_baselinejson)
   - [3.3 run_experiment.py](#33-run_experimentpy)
   - [3.4 run_judge.py](#34-run_judgepy)
   - [3.5 compare_runs.py](#35-compare_runspy)
4. [Operational Guide](#operational-guide)
5. [Complete Workflow Examples](#complete-workflow-examples)
6. [Troubleshooting](#troubleshooting)
7. [Implementation Quality Summary](#implementation-quality-summary)

---

## 1. Overview

The `eval/` folder contains the **Delta Evaluation Framework** for HOM-LLM v2.0. This framework enables:

- **Experiment Execution**: Running selected test queries through the HOM-LLM pipeline
- **Quality Judging**: LLM-based comparison of HOM-LLM responses against the Cursor baseline
- **Run Comparison**: Delta analysis between different experiment runs

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Read-Only** | Does not modify core HOM-LLM modules |
| **Subprocess Isolation** | Uses subprocess to call runtime, ensuring isolation |
| **Append-Only** | Response storage uses JSONL format for append-only writes |
| **Flexible Selection** | Supports various query selection expressions |

---

## 2. Folder Structure

```
eval/
├── queries.json           # 20 canonical test queries
├── cursor_baseline.json   # Reference answers from Cursor (Gemini 2.5 Flash)
├── run_experiment.py      # Experiment runner (invokes runtime/run_query.py)
├── run_judge.py           # LLM-based judge for quality comparison
├── compare_runs.py        # Delta comparison between two runs
├── runs/                  # Output directory for experiment runs
│   └── run_YYYYMMDD_HHMMSS/
│       ├── run_info.json       # Run metadata
│       └── responses.jsonl     # Query responses
└── generated_answers/     # Persisted answer text files (auto-generated)
```

---

## 3. File Analysis & Implementation Review

### 3.1 `queries.json`

#### Purpose
Defines the canonical set of 20 test queries used for evaluation. These queries are designed to test various aspects of code understanding and retrieval.

#### Schema Structure
```json
{
    "metadata": {
        "total_queries": 20,
        "description": "All 20 test queries extracted from cursor_baseline.json"
    },
    "queries": [
        {
            "query_id": 1,
            "query_text": "..."
        }
    ]
}
```

#### Query Categories
The 20 queries cover diverse topics:

| ID Range | Topic Area |
|----------|------------|
| 1-3 | Execution flow, tracing, query optimization |
| 4-6 | Job lifecycle, caching, call-graph traversal |
| 7-10 | Search fallbacks, connection pooling, ranking, JWT |
| 11-14 | Embeddings, metrics, NaN handling, input validation |
| 15-18 | Schema evolution, batch processing, eviction, optimization |
| 19-20 | Redis serialization, stress testing |

#### Implementation Status: ✅ **CORRECTLY IMPLEMENTED**

**Strengths:**
- Well-structured JSON format
- Clear metadata section
- Unique query IDs for tracking
- Diverse query complexity levels

---

### 3.2 `cursor_baseline.json`

#### Purpose
Contains reference answers from Cursor (using Gemini 2.5 Flash) for all 20 test queries. These serve as the **baseline** for judging HOM-LLM responses.

#### Schema Structure
```json
{
    "metadata": {
        "version": "2.0",
        "description": "Cursor baseline - ...",
        "system": "Cursor (Gemini 2.5 Flash)",
        "creation_date": "2025-12-07",
        "total_queries": 20
    },
    "queries": [
        {
            "query_id": 1,
            "query_text": "...",
            "answer": "..."
        }
    ]
}
```

#### Implementation Status: ✅ **CORRECTLY IMPLEMENTED**

**Strengths:**
- Comprehensive metadata for traceability
- Detailed, high-quality reference answers (150-300+ words each)
- Aligned query_id mapping with `queries.json`
- Includes code snippets and structured explanations

**Note:** The answers are substantial and professionally written, providing a high-quality baseline for comparison.

---

### 3.3 `run_experiment.py`

#### Purpose
The main experiment runner that executes selected queries through the HOM-LLM runtime and stores responses for downstream judging.

#### Key Components

| Component | Lines | Description |
|-----------|-------|-------------|
| `SelectionError` | 33-34 | Custom exception for query selection errors |
| `parse_selection()` | 37-72 | Parses selection expressions (e.g., "1,5,7", "1-10", "all") |
| `QueryRecord` | 75-78 | Dataclass for query storage |
| `load_queries()` | 81-85 | Loads queries from `queries.json` |
| `extract_result_text()` | 88-106 | Parses answer from runtime stdout |
| `extract_telemetry_path()` | 109-114 | Extracts telemetry JSON path |
| `run_single_query()` | 184-247 | Core function: runs one query via subprocess |
| `persist_answer_txt()` | 250-265 | Saves human-readable answer files |
| `write_jsonl()` | 268-271 | JSONL append writer |
| `main()` | 288-337 | CLI entry point with argparse |

#### Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--select` | str | "all" | Query selection expression |
| `--config` | Path | configs/default.yaml | Config file path |
| `--provider` | str | None | LLM provider override |
| `--model` | str | None | Model name override |
| `--intent` | str | None | Query intent |
| `--raw` | flag | False | Pass --raw to runtime |
| `--no-file-mapping` | flag | False | Disable file-id mapping |
| `--run-name` | str | auto | Custom run name |
| `--output-dir` | Path | eval/runs | Output directory |
| `--telemetry-print` | flag | True | Print telemetry summary |

#### Implementation Status: ✅ **CORRECTLY IMPLEMENTED**

**Strengths:**
- Clean subprocess isolation from core modules
- Flexible query selection (single, range, comma-separated, all)
- Comprehensive telemetry extraction and display
- JSONL append-only storage for robustness
- Auto-generated run names with timestamps
- Persists both structured (JSONL) and human-readable (.txt) answers

**Code Quality Highlights:**
```python
# Selection parsing supports multiple formats
def parse_selection(expr: str, total: int) -> List[int]:
    expr = expr.strip().lower()
    if expr == "all":
        return list(range(1, total + 1))
    # Supports: "3", "1,5,7", "1-10"
```

---

### 3.4 `run_judge.py`

#### Purpose
LLM-based judge that compares HOM-LLM answers against the Cursor baseline, producing structured quality scores.

#### Key Components

| Component | Lines | Description |
|-----------|-------|-------------|
| `JudgeConfig` | 46-50 | Dataclass for judge LLM configuration |
| `load_judge_config()` | 53-60 | Loads judge config from JSON |
| `build_prompt()` | 63-84 | Constructs the comparison prompt |
| `ensure_openai_client()` | 87-98 | Initializes OpenAI client |
| `call_judge()` | 101-115 | Calls the judge LLM |
| `main()` | 118-169 | CLI entry point |

#### Scoring Dimensions

The judge evaluates on 8 dimensions:

| Dimension | Scale | Description |
|-----------|-------|-------------|
| `semantic_correctness` | 1-5 | Accuracy of meaning |
| `factual_consistency` | 1-5 | Consistency with code facts |
| `completeness` | 1-5 | Coverage of the answer |
| `clarity` | 1-5 | Readability and structure |
| `relevance` | 1-5 | How well it addresses the query |
| `hallucination_risk` | 1-5 | 1=risky, 5=safe |
| `verbosity` | 1-5 | Lower is better |
| `overall_quality` | 1-5 | Aggregate quality score |

#### Output Schema
```json
{
    "query_id": 1,
    "query_text": "...",
    "candidate_model": "...",
    "candidate_provider": "...",
    "baseline_system": "Cursor",
    "judge_model": "...",
    "scores": { /* 8 dimensions */ },
    "verdict": "improved|equal|regressed",
    "explanation": "...",
    "key_differences": ["..."],
    "timestamp": "..."
}
```

#### Implementation Status: ✅ **CORRECTLY IMPLEMENTED**

**Strengths:**
- Clear separation from core HOM-LLM modules
- OpenAI-compatible API (works with various providers)
- Structured JSON output with `response_format`
- Append-only output for robustness
- Comprehensive error handling
- Well-defined scoring rubric

**Required Configuration (`judge_config.json`):**
```json
{
    "model": "gpt-4o-mini",
    "api_key": "your-api-key",
    "base_url": "https://api.openai.com/v1"  // Optional
}
```

---

### 3.5 `compare_runs.py`

#### Purpose
Compares judge results between two experiment runs, computing deltas and generating reports.

#### Key Components

| Component | Lines | Description |
|-----------|-------|-------------|
| `read_jsonl()` | 14-22 | JSONL file reader |
| `load_scores()` | 25-27 | Loads scores keyed by query_id |
| `delta()` | 30-31 | Computes score difference |
| `summarize()` | 34-56 | Aggregates deltas across queries |
| `write_csv()` | 59-68 | Exports delta report to CSV |
| `write_markdown()` | 71-86 | Exports delta report to Markdown |
| `main()` | 89-123 | CLI entry point |

#### Command-Line Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `--a` | str | Baseline (older) run name/path |
| `--b` | str | New run name/path |
| `--runs-dir` | Path | Base directory for runs (default: eval/runs) |

#### Output Files
- `delta.csv` - CSV format for data analysis
- `delta.md` - Markdown format for human review

#### Implementation Status: ✅ **CORRECTLY IMPLEMENTED**

**Strengths:**
- Clean comparison logic
- Dual output formats (CSV + Markdown)
- Handles missing queries gracefully
- Clear aggregate delta calculation
- Auto-generated output directory names

---

## 4. Operational Guide

### 4.1 Prerequisites

Before running evaluations, ensure:

1. **Python Environment**: Python 3.9+ with required packages
2. **HOM-LLM Setup**: Core pipeline configured and working
3. **Index Artifacts**: Vector index created via indexer pipeline
4. **LLM Provider**: API key configured for generation
5. **Judge Config**: `judge_config.json` created (for judging)

### 4.2 Step-by-Step Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  run_experiment │ ──▶ │    run_judge    │ ──▶ │  compare_runs   │
│   .py           │     │      .py        │     │      .py        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     │                        │                        │
     ▼                        ▼                        ▼
  responses.jsonl       judge_results.jsonl       delta.csv/md
```

---

## 5. Complete Workflow Examples

### Example 1: Run All Queries

**Command:**
```powershell
cd d:\HOM-LLM(v2.0)
python eval/run_experiment.py --select all --config configs/default.yaml --provider gemini --model gemini-2.0-flash
```

**Expected Output:**
```
[QUERY 01 COMPLETED]
Run ID      : run_20260121_163422
Query       : Trace the execution flow when an admin user calls the admin_search_endpoint...

RETRIEVAL   : 245 ms | candidates=50 (bm25=25, vector=25)
RANKING     : 89 ms | reranker=True
CONTEXT     : 32 ms | blocks=12 tokens=3500/8192
GENERATION  : 1523 ms | model=gemini-2.0-flash | in=4200 out=450 | status=OK
--------------------------------------------------
[RUN 1/20] Query 01 ✔ OK
[RUN 2/20] Query 02 ✔ OK
...
Saved responses to: eval/runs/run_20260121_163422/responses.jsonl
```

### Example 2: Run Specific Queries

**Single Query:**
```powershell
python eval/run_experiment.py --select 5
```

**Multiple Specific Queries:**
```powershell
python eval/run_experiment.py --select 1,5,10,15
```

**Range of Queries:**
```powershell
python eval/run_experiment.py --select 1-10
```

**Mixed Selection:**
```powershell
python eval/run_experiment.py --select 1-5,8,12-15
```

### Example 3: Run with Custom Settings

```powershell
python eval/run_experiment.py ^
    --select all ^
    --config configs/production.yaml ^
    --provider openai ^
    --model gpt-4o ^
    --run-name "gpt4o_baseline_v1" ^
    --output-dir eval/runs
```

### Example 4: Judge Experiment Results

**Command:**
```powershell
python eval/run_judge.py ^
    --responses eval/runs/run_20260121_163422/responses.jsonl ^
    --baseline eval/cursor_baseline.json ^
    --judge-config eval/judge_config.json
```

**Sample `judge_config.json`:**
```json
{
    "model": "gpt-4o-mini",
    "api_key": "sk-your-api-key-here",
    "base_url": null
}
```

**Expected Output:**
```
Saved judge results to: eval/runs/run_20260121_163422/judge_results.jsonl
```

**Sample Judge Result:**
```json
{
    "query_id": 1,
    "query_text": "Trace the execution flow...",
    "candidate_model": "gemini-2.0-flash",
    "candidate_provider": "gemini",
    "baseline_system": "Cursor",
    "judge_model": "gpt-4o-mini",
    "scores": {
        "semantic_correctness": 4,
        "factual_consistency": 4,
        "completeness": 5,
        "clarity": 4,
        "relevance": 5,
        "hallucination_risk": 4,
        "verbosity": 3,
        "overall_quality": 4
    },
    "verdict": "improved",
    "explanation": "The candidate answer provides more specific code references...",
    "key_differences": [
        "Candidate includes actual line numbers",
        "Candidate explains decorator chain in more detail"
    ],
    "timestamp": "2026-01-21T16:45:30Z"
}
```

### Example 5: Compare Two Runs

**Command:**
```powershell
python eval/compare_runs.py ^
    --a run_20260120_baseline ^
    --b run_20260121_improved ^
    --runs-dir eval/runs
```

**Expected Output:**
```
Wrote delta CSV: eval/runs/compare_run_20260120_baseline_vs_run_20260121_improved/delta.csv
Wrote delta Markdown: eval/runs/compare_run_run_20260120_baseline_vs_run_20260121_improved/delta.md
Average overall delta: +0.45
```

**Sample Markdown Report:**
```markdown
# Delta Report: run_20260120_baseline → run_20260121_improved

- Average overall delta: +0.45

| Query | Overall A | Overall B | Δ | Verdict A | Verdict B |
|-------|-----------|-----------|---|-----------|-----------|
| 01 | 3.50 | 4.00 | +0.50 | equal | improved |
| 02 | 4.00 | 4.50 | +0.50 | improved | improved |
| 03 | 3.00 | 3.50 | +0.50 | regressed | equal |
...
```

### Example 6: Full Evaluation Pipeline Script

Create a script `eval/run_full_eval.ps1`:

```powershell
# Full Evaluation Pipeline Example
# Usage: .\eval\run_full_eval.ps1 -Provider gemini -Model gemini-2.0-flash

param(
    [string]$Provider = "gemini",
    [string]$Model = "gemini-2.0-flash",
    [string]$Selection = "all"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runName = "eval_${Provider}_${timestamp}"

Write-Host "=== Starting HOM-LLM Evaluation ===" -ForegroundColor Cyan
Write-Host "Provider: $Provider"
Write-Host "Model: $Model"
Write-Host "Run Name: $runName"

# Step 1: Run Experiment
Write-Host "`n[1/3] Running experiment..." -ForegroundColor Yellow
python eval/run_experiment.py `
    --select $Selection `
    --provider $Provider `
    --model $Model `
    --run-name $runName

# Step 2: Run Judge
Write-Host "`n[2/3] Running judge..." -ForegroundColor Yellow
python eval/run_judge.py `
    --responses "eval/runs/$runName/responses.jsonl" `
    --baseline eval/cursor_baseline.json `
    --judge-config eval/judge_config.json `
    --output "eval/runs/$runName/judge_results.jsonl"

Write-Host "`n=== Evaluation Complete ===" -ForegroundColor Green
Write-Host "Results saved to: eval/runs/$runName/"
```

---

## 6. Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `SelectionError: Range out of bounds` | Selection exceeds total queries | Use 1-20 range only |
| `Missing baseline for query_id X` | Query ID mismatch | Ensure query_id alignment |
| `openai package required` | Missing dependency | Run `pip install openai` |
| `judge_config.json must include 'model' and 'api_key'` | Invalid config | Check judge config format |
| `Failed to generate query embedding` | Indexer not configured | Run indexer pipeline first |
| `No queries selected` | Invalid selection syntax | Use formats: all, 5, 1-10, 1,5,10 |

### Debug Commands

**Check Query Count:**
```powershell
python -c "import json; print(len(json.load(open('eval/queries.json'))['queries']))"
```

**Validate Judge Config:**
```powershell
python -c "import json; cfg=json.load(open('eval/judge_config.json')); print('OK' if cfg.get('model') and cfg.get('api_key') else 'INVALID')"
```

**List Available Runs:**
```powershell
Get-ChildItem eval/runs -Directory | Select-Object Name
```

---

## 7. Implementation Quality Summary

### Overall Assessment: ✅ **PRODUCTION READY**

| File | Status | Quality Score |
|------|--------|---------------|
| `queries.json` | ✅ Correct | 5/5 |
| `cursor_baseline.json` | ✅ Correct | 5/5 |
| `run_experiment.py` | ✅ Correct | 5/5 |
| `run_judge.py` | ✅ Correct | 5/5 |
| `compare_runs.py` | ✅ Correct | 5/5 |

### Positive Findings

1. **Clean Architecture**: Strong separation of concerns between experiment running, judging, and comparison
2. **Robust Error Handling**: Comprehensive try-except blocks with informative error messages
3. **Flexible Configuration**: CLI arguments provide extensive customization
4. **Append-Only Design**: JSONL output prevents data corruption from interrupted runs
5. **Telemetry Integration**: Detailed performance metrics extraction
6. **Dual Output Formats**: Both structured (JSON/CSV) and human-readable (Markdown/TXT)

### Recommendations for Future Enhancement

1. **Parallel Query Execution**: Add `--parallel N` flag for faster batch runs
2. **Resume Capability**: Track completed queries to enable run resumption
3. **Score Visualization**: Add a script to generate charts from judge results
4. **Automated Regression Detection**: Alert when delta falls below threshold

---

## Appendix: Quick Reference Card

```
┌────────────────────────────────────────────────────────────────────┐
│                    HOM-LLM EVAL QUICK REFERENCE                     │
├────────────────────────────────────────────────────────────────────┤
│ RUN EXPERIMENT:                                                     │
│   python eval/run_experiment.py --select all --provider gemini     │
│                                                                     │
│ SELECTION SYNTAX:                                                   │
│   all       → All 20 queries                                       │
│   5         → Query 5 only                                         │
│   1,5,10    → Queries 1, 5, and 10                                 │
│   1-10      → Queries 1 through 10                                 │
│   1-5,8,12  → Mixed selection                                      │
│                                                                     │
│ RUN JUDGE:                                                          │
│   python eval/run_judge.py --responses <path> --baseline <path>    │
│                            --judge-config eval/judge_config.json   │
│                                                                     │
│ COMPARE RUNS:                                                       │
│   python eval/compare_runs.py --a <run1> --b <run2>                │
│                                                                     │
│ OUTPUT LOCATIONS:                                                   │
│   Responses:     eval/runs/<run_name>/responses.jsonl              │
│   Judge Results: eval/runs/<run_name>/judge_results.jsonl          │
│   Delta Report:  eval/runs/compare_<a>_vs_<b>/delta.md             │
│   Answer Texts:  eval/generated_answers/query_XX_<run_id>.txt      │
└────────────────────────────────────────────────────────────────────┘
```

---

*Report generated by HOM-LLM Documentation System*
