# Runtime Layer with Telemetry

This directory contains canonical entrypoints for running HOM-LLM operations with built-in telemetry.

## Entrypoints

### `index_repo.py` - Index a Repository

Indexes a codebase and generates all required artifacts.

**Usage:**
```bash
python runtime/index_repo.py --repo <path> [options]
```

**Options:**
- `--repo <path>` (required): Path to repository root
- `--config <path>`: Config file path (default: `configs/default.yaml`)
- `--incremental`: Enable incremental indexing
- `--json`: Export JSON telemetry to `indexes/index_telemetry.json`
- `--progress-interval <seconds>`: Progress update interval (default: 5 seconds)

**Example:**
```bash
python runtime/index_repo.py --repo ./test_repo --json
```

**Telemetry Output:**
```
[INDEX] start=2024-01-01T12:00:00 repo=./test_repo
[INDEX] status=processing elapsed_ms=5000
[INDEX] status=processing elapsed_ms=10000
[INDEX] end=2024-01-01T12:00:30 files=123 symbols=456 duration_ms=30000
[INDEX] artifact=indexes/symbols.json
[INDEX] artifact=indexes/files.json
[INDEX] artifact=indexes/callgraph.json
```

---

### `run_query.py` - Run a Query End-to-End

Executes a query through the full pipeline: retrieval → ranking → context → generation.

**Usage:**
```bash
python runtime/run_query.py --query "..." [options]
```

**Options:**
- `--query <text>` (required): Query string
- `--config <path>`: Config file path (default: `configs/default.yaml`)
- `--json`: Export JSON telemetry to `artifacts/runs/<run_id>/telemetry.json`
- `--provider <name>`: Generation provider (gemini, openai, local)
- `--model <name>`: Generation model name
- `--intent <name>`: Query intent (default: UNKNOWN)

**Example:**
```bash
python runtime/run_query.py --query "How does authentication work?" --provider gemini --json
```

**Telemetry Output:**
```
[RETRIEVAL] start=2024-01-01T12:00:00 duration_ms=150 candidates=50 bm25_count=25 vector_count=25 merged_count=50
[RANKING] start=2024-01-01T12:00:00 duration_ms=200 candidates=50 reranker=true reranker_unavailable=false
[CONTEXT] start=2024-01-01T12:00:00 duration_ms=50 blocks=8 tokens=3200 token_budget=4000
[GENERATION] start=2024-01-01T12:00:00 duration_ms=1200 provider=gemini model=gemini-3.5-flash-lite tokens_in=3200 tokens_out=500 status=OK
```

---

## Telemetry Format

All telemetry follows a consistent format:
```
[PHASE] key1=value1 key2=value2 ...
```

**Timing:**
- All durations are in milliseconds (ms)
- Timestamps are ISO-8601 format
- Uses `time.perf_counter()` for accurate timing

**Phase Names:**
- `INDEX`: Indexing phase
- `RETRIEVAL`: Retrieval phase
- `RANKING`: Ranking phase
- `CONTEXT`: Context assembly phase
- `GENERATION`: Generation phase
- `TELEMETRY`: Telemetry export notification

---

## JSON Export

When `--json` is specified:

- **Indexing**: Writes to `indexes/index_telemetry.json`
- **Query**: Writes to `artifacts/runs/<run_id>/telemetry.json`

JSON structure:
```json
{
  "phase": "indexing" | "query",
  "repo_path": "...",
  "start_time": "2024-01-01T12:00:00",
  "end_time": "2024-01-01T12:00:30",
  "duration_ms": 30000,
  "phases": {
    "RETRIEVAL": { ... },
    "RANKING": { ... },
    ...
  }
}
```

---

## Progress Visibility

During long indexing runs, progress updates are printed periodically:
- Default: Every 5 seconds
- Configurable via `--progress-interval`
- Shows elapsed time and status

---

## Safety & Determinism

- **No core logic changes**: All telemetry is observational only
- **No side effects**: Telemetry wrappers don't mutate inputs/outputs
- **Determinism preserved**: Timing measurements don't affect results
- **Thread-safe**: Progress updates use daemon threads

---

## Migration from Old Scripts

- `indexes_maker.py` → `runtime/index_repo.py`
- Old scripts are deprecated but redirect to new entrypoints for backward compatibility

---

## Requirements

- Python 3.8+
- All dependencies from `pyproject.toml`
- Valid config file (default: `configs/default.yaml`)
