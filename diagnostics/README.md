# HOM-LLM Diagnostic Framework

A **read-only observability system** for deep introspection into all non-generation phases of the HOM-LLM pipeline:

**Embedding → Retrieval → Expansion → Re-ranking → Context Assembly**

This system exists to **explain why the system behaves the way it does**, not to change behavior.

---

## Purpose

* A long-term experimentation and debugging layer
* A forensic tool to understand signal vs noise
* A visibility layer for architecture-level decisions
* A foundation for future optimizations and intelligence layers

This system does **NOT**:
* ❌ Mutate core HOM-LLM logic
* ❌ Provide feedback into retrieval, ranking, or context selection
* ❌ Depend on LLM generation or prompts
* ❌ Act as an evaluation/scoring system

---

## Directory Structure

```
diagnostics/
├── embedding/
│   └── inspect_embeddings.py    # Chunk size distribution, waste analysis
├── retrieval/
│   └── inspect_retrieval.py     # BM25 vs vector overlap, dominance
├── reranking/
│   └── inspect_reranking.py     # Rank churn, stability, bias detection
├── context/
│   └── inspect_context.py       # Block selection, token budgets, redundancy
├── common/
│   ├── loaders.py               # Read-only data loaders
│   ├── formatters.py            # Terminal, JSON, Markdown output
│   └── utils.py                 # Query selectors, statistics
├── reports/
│   ├── per_query/               # Per-query diagnostic reports
│   └── summary/                 # Aggregated summary reports
└── run_diagnostics.py           # Main CLI entry point
```

---

## Quick Start

### List available runs:
```bash
python diagnostics/run_diagnostics.py --list-runs
```

### Analyze a specific run:
```bash
python diagnostics/run_diagnostics.py --run-id <run_id> --phases context,retrieval,reranking
```

### Run embedding waste analysis:
```bash
python diagnostics/run_diagnostics.py --embedding-analysis
```

### Analyze with different output formats:
```bash
# Terminal (default)
python diagnostics/run_diagnostics.py --run-id <run_id> --format terminal

# JSON (machine-readable)
python diagnostics/run_diagnostics.py --run-id <run_id> --format json

# Markdown (for documentation)
python diagnostics/run_diagnostics.py --run-id <run_id> --format markdown --save-report
```

### Analyze specific queries:
```bash
# Single query
python diagnostics/run_diagnostics.py --query 3 --phases all

# Range of queries
python diagnostics/run_diagnostics.py --query 1-10 --phases context

# Multiple queries
python diagnostics/run_diagnostics.py --query 1,5,7 --phases retrieval
```

---

## Phase-Wise Diagnostics

### 1. Embedding Diagnostics

Analyzes the embedding index to understand chunk distribution and waste.

**Metrics:**
- Total embeddings (symbols, files)
- Text length distribution (avg, median, min, max)
- Token count distribution
- Size buckets (undersized <50, optimal 50-500, oversized >500)
- Never-retrieved percentage (if retrieval data available)

**Warnings:**
- Many undersized chunks (inefficient encoding)
- Many oversized chunks (potential truncation)
- High never-retrieved percentage (waste)

### 2. Retrieval Diagnostics

Analyzes BM25 vs vector retrieval overlap and effectiveness.

**Metrics:**
- BM25 candidate count
- Vector candidate count
- Merged candidate count
- Overlap count and ratio
- Dominance percentages
- Retrieval duration

**Warnings:**
- Both searches failed
- Very low overlap (methods disagreeing)
- Slow retrieval (>5s)

### 3. Re-ranking Diagnostics

Analyzes the quality impact of the reranker (not performance).

**Metrics:**
- Candidate count
- Reranker used/unavailable status
- Rank churn percentage
- Top-N stability
- Average/max rank delta
- Length bias score
- Top promotions/demotions

**Warnings:**
- Reranker unavailable
- High rank churn (>80%)
- Low top-N stability (<50%)
- Possible length bias (correlation >0.5)

### 4. Context Diagnostics (Highest Priority)

Explains what the model sees and why.

**Metrics:**
- Total blocks and tokens
- Token budget utilization
- Top-K token concentration
- Structural vs semantic dominance
- Redundant blocks detection

**Warnings:**
- Near budget limit (>95%)
- Empty context
- High token concentration in few blocks
- Multiple blocks from same file (redundancy)

---

## Output Formats

### Terminal
Human-readable, structured output. No ANSI codes, no emojis.
```
[CONTEXT DIAGNOSTIC]
Run ID: abc123

Total Blocks: 22
Total Tokens: 3184
Token Budget: 4000
Used Budget Pct: 79.6%

! Near budget limit: 79.6% used
```

### JSON
Machine-readable with deterministic key ordering.
```json
{
  "phase": "context",
  "run_id": "abc123",
  "summary": {...},
  "warnings": [...]
}
```

### Markdown
For documentation and analysis reports with tables.

---

## Data Sources (Read-Only)

The diagnostic system only reads from:

| Source | Description |
|--------|-------------|
| `indexes/` | Embedding metadata (symbols.json, files.json) |
| `artifacts/runs/*/telemetry.json` | Per-run phase metrics |
| `eval/queries.json` | Query definitions |
| `eval/runs/*/responses.jsonl` | Eval run responses |

**No new artifacts are created in the core system.**

---

## Long-Term Design Principles

1. **Stable under model swaps** - Works regardless of which LLM is used
2. **Deterministic and replayable** - Same inputs always produce same outputs
3. **Independent from agentic layers** - No coupling to controllers or feedback loops
4. **Supports run diffing** - Compare metrics across different runs

---

## Success Criteria

This diagnostic framework is successful if it can:

✓ Explain **why context is large**  
✓ Identify **noise sources**  
✓ Reveal **ineffective retrieval or ranking**  
✓ Justify architectural changes with evidence  
✓ Prevent blind optimization

---

## Implementation Priority

1. ✅ Context diagnostics (block-level, token-level)
2. ✅ Retrieval overlap & dominance
3. ✅ Re-ranking quality impact
4. ✅ Embedding waste analysis

---

## Core Constraints

These constraints must **never** be violated:

* ❌ No mutation of core HOM-LLM logic
* ❌ No imports that change runtime behavior
* ❌ No feedback into retrieval, ranking, or context selection
* ❌ No dependency on LLM generation or prompts
* ❌ No JSON schema enforcement on core outputs
* ✅ Strictly read-only
* ✅ Model-agnostic
* ✅ Deterministic and replayable
* ✅ Can be disabled or removed without affecting core system
