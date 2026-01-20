# HOM-LLM (v2.0)

Cursor-class deterministic RAG engine for code intelligence.

## Architecture

This project implements a strict 5-phase pipeline:
1. **Indexer** - Transforms codebase into structured intelligence
2. **Retrieval** - Hybrid BM25 + vector search
3. **Ranking** - Deterministic scoring and reranking
4. **Context Assembly** - Token-budgeted context curation
5. **Generation** - Provider-agnostic LLM adapter

See `CompleteArchitecturePlan_Refined.md` for the canonical architecture.

## Principles

- **Deterministic**: Same inputs + same config → same outputs
- **Replaceable**: Every component sits behind an interface
- **Offline**: No network calls during indexing
- **Model-agnostic**: Swappable embeddings, rerankers, generators
- **Immutable artifacts**: Index outputs are write-once

## Installation

```bash
pip install -e .
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/

# Lint
ruff check src/
```

## Status

🚧 **Under active development** - Phase 1 (Indexer) in progress.
