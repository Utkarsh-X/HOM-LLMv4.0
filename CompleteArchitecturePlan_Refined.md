# Cursor‑Class RAG Architecture – Core Foundations (v2.2 REFINED)

This document captures the **permanent architectural foundation** for a Cursor‑class code intelligence system. This is the reference design. It is intentionally minimal, modular, resistant to over‑engineering, and API‑agnostic.

This document exists so architecture decisions are never lost or mutated.

> **DOCUMENT STATUS**: Canonical reference. Immutable in spirit.  
> **VERSION**: 2.2 (Refined from v2.1)  
> **REFINEMENT SCOPE**: Strengthened invariants, explicit contracts, failure modes, non-goals, and anti-patterns. No architectural changes.

---

## Table of Contents

1. [Design Principles](#design-principles)
2. [Architectural Invariants](#architectural-invariants)
3. [System Stack Overview](#system-stack-overview)
4. [Indexer Layer (Phase 1)](#indexer-layer-foundation)
5. [Retrieval Layer (Phase 2)](#retrieval--phase-2)
6. [Ranking Layer (Phase 3)](#ranking-layer-architecture)
7. [Context Assembly (Phase 4)](#context-assembly-architecture)
8. [Generation Phase (Phase 5)](#generation-phase-detailed-architecture)
9. [Evaluation Framework](#evaluation-framework--cli--design--architecture)
10. [Forbidden Patterns (Global)](#forbidden-patterns-global)
11. [Testing Implications](#testing-implications)
12. [Observability Contract](#observability-contract)

---

## Design Principles

### Core Tenets

| # | Principle | Definition | Violation Example |
|---|-----------|------------|-------------------|
| 1 | **Primitive‑First Architecture** | Build on proven infrastructure primitives, not abstractions. | Using a custom ORM instead of raw SQL; inventing a "universal store" |
| 2 | **Replaceable Components** | Every subsystem must be swappable without breaking others. | Direct imports between layers; hardcoded model names |
| 3 | **No Intelligence Layer** | Intelligence emerges from retrieval quality, not orchestration. | Adding a "query router" that decides retrieval strategy |
| 4 | **No Agents** | Cursor does not use agents. Neither will we. | Adding autonomous retry loops; self-modifying prompts |
| 5 | **Strict Module Boundaries** | No cross‑imports between layers. | `context/` importing from `generation/` |
| 6 | **Deterministic Execution** | No hidden control flow, no magic routing. | Random sampling in ranking; time-based logic |
| 7 | **Evaluation Is External** | Never inside core logic. | Judge scores influencing retrieval order |

### Principle Enforcement

Each principle MUST be verifiable through static analysis or unit tests:

```
Principle 2 → "grep -r 'from homllm.generation' src/homllm/retrieval/" returns empty
Principle 5 → Import graph analysis shows DAG with no upward edges
Principle 6 → Same input files + same config → byte-identical index artifacts
```

---

## Architectural Invariants

These invariants are **unconditional**. No feature, optimization, or experiment may violate them.

### Global Invariants

| ID | Invariant | Rationale |
|----|-----------|-----------|
| INV-001 | **Indexer produces truth; all other layers consume it** | Single source of truth prevents drift |
| INV-002 | **No layer may modify artifacts produced by a prior layer** | Immutability enables caching, debugging, replay |
| INV-003 | **All thresholds, weights, and magic numbers live in config** | Prevents hidden tuning; enables A/B testing |
| INV-004 | **No runtime behavior depends on repository identity** | Prevents overfitting to test repos |
| INV-005 | **Evaluation code has zero imports from core pipeline** | Prevents evaluation feedback loops |
| INV-006 | **Every external dependency sits behind an adapter interface** | Enables replacement without refactoring |
| INV-007 | **Same inputs + same config = same outputs** | Determinism is testable |

### Layer-Specific Invariants

| Layer | Invariant |
|-------|-----------|
| Indexer | MUST NOT import LLM, API, or model modules |
| Retrieval | MUST NOT modify index artifacts |
| Ranking | MUST NOT call generation or evaluation |
| Context | MUST NOT embed model-specific token limits |
| Generation | MUST NOT contain retrieval or ranking logic |

---

## Non-Goals (What This System Will NEVER Do)

Explicitly stating non-goals prevents future scope creep.

| Category | Non-Goal | Why |
|----------|----------|-----|
| Autonomy | Autonomous multi-step reasoning | Agents introduce non-determinism and debugging complexity |
| Learning | Online learning from user feedback | Creates feedback loops; evaluation must remain external |
| Routing | Dynamic model selection based on query | Intelligence layer; breaks determinism |
| Caching | Intelligent cache invalidation | Heuristic; use explicit version hashes instead |
| Optimization | Automatic threshold tuning | Overfitting risk; config must be explicit |
| Integration | Direct IDE/editor coupling in core | Core is headless; integrations are separate adapters |

---

## System Stack Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CORE PIPELINE                            │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│   Indexer   │  Retrieval  │   Ranking   │   Context   │  Gen    │
│  (Phase 1)  │  (Phase 2)  │  (Phase 3)  │  (Phase 4)  │(Phase 5)│
├─────────────┴─────────────┴─────────────┴─────────────┴─────────┤
│                      IMMUTABLE ARTIFACTS                         │
│  symbols.json │ callgraph.json │ bm25.index/ │ vectors.lance/   │
├─────────────────────────────────────────────────────────────────┤
│                      STORAGE ADAPTERS                            │
│     DuckDB    │    Tantivy    │   LanceDB   │   Filesystem      │
├─────────────────────────────────────────────────────────────────┤
│                      EXTERNAL (ISOLATED)                         │
│                Evaluation │ CLI │ GUI │ Adapters                │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Contract

```
Repo (immutable input)
     │
     ▼
┌─────────────┐
│   Indexer   │──────► Immutable Artifacts (symbols, graphs, indexes)
└─────────────┘
     │
     ▼ (read-only)
┌─────────────┐
│  Retrieval  │──────► Candidate List (scored, unordered)
└─────────────┘
     │
     ▼
┌─────────────┐
│   Ranking   │──────► Ranked Candidate List (deterministic order)
└─────────────┘
     │
     ▼
┌─────────────┐
│   Context   │──────► Context Artifact (token-budgeted, ordered blocks)
└─────────────┘
     │
     ▼
┌─────────────┐
│ Generation  │──────► Response Artifact (raw text + metadata)
└─────────────┘
```

**Contract**: Each arrow represents a typed interface. Downstream layers receive immutable artifacts; they MUST NOT mutate them.

---

# INDEXER LAYER (Foundation)

The indexer is the most important layer.  
If this is wrong, everything is wrong.

## Purpose

Transforms raw codebase into structured intelligence.

## Indexer Invariants

| ID | Invariant | Test |
|----|-----------|------|
| IDX-001 | Same repo state → byte-identical artifacts | Hash comparison after two runs |
| IDX-002 | No network calls during indexing | Mock all I/O; verify no HTTP |
| IDX-003 | Incremental = full on changed files only | Diff file list; verify subset indexed |
| IDX-004 | Language parsers are isolated | Parser crash in Python does not affect JS |

## Indexer Non-Goals

- MUST NOT perform query routing
- MUST NOT call embedding APIs (embeddings are produced by a pluggable local model)
- MUST NOT read evaluation results
- MUST NOT contain retry logic
- MUST NOT implement caching (caching is a storage adapter concern)

## Indexer Outputs (Immutable Artifacts)

```
/index
  ├── symbols.json        # Symbol table: names, types, locations
  ├── files.json          # File metadata: paths, hashes, languages
  ├── callgraph.json      # Static call graph edges
  ├── dependencies.json   # Import/export relationships
  ├── bm25.index/         # Tantivy inverted index
  ├── vectors.lance/      # LanceDB vector index
  └── metadata.duckdb     # Relational metadata + graph edges
```

### Artifact Schema Contracts

**symbols.json**
```json
{
  "version": "1.0",
  "symbols": [
    {
      "id": "string (unique)",
      "name": "string",
      "kind": "function|class|method|variable|constant",
      "file": "string (relative path)",
      "start_line": "integer",
      "end_line": "integer",
      "signature": "string (optional)",
      "decorators": ["string"],
      "parent_id": "string|null"
    }
  ]
}
```

**callgraph.json**
```json
{
  "version": "1.0",
  "edges": [
    {
      "caller_id": "string",
      "callee_id": "string",
      "call_site_line": "integer"
    }
  ]
}
```

### Schema Versioning Contract

- Every artifact file includes a `version` field
- Version format: `MAJOR.MINOR`
- MAJOR increment = breaking change; requires re-index
- MINOR increment = backward-compatible addition
- Consumers MUST check version before parsing

---

## Indexer Subsystems

### 1. File Scanner

**Tool:** ripgrep

**Interface Contract:**
```python
class FileScanner(Protocol):
    def scan(self, repo_path: Path, config: ScanConfig) -> Iterator[FileInfo]:
        """Yields file metadata without loading content."""
        ...
```

**Properties:**
- Respects `.gitignore` by default
- Language filters are config-driven (not hardcoded)
- Returns deterministic ordering (sorted by path)

### 2. Code Parser

**Tool:** Tree‑Sitter

**Interface Contract:**
```python
class CodeParser(Protocol):
    def parse(self, file_path: Path, language: str) -> ParseResult:
        """Returns AST and extracted symbols."""
        ...
    
    def supported_languages(self) -> list[str]:
        """Returns list of parseable languages."""
        ...
```

**Failure Handling:**
- Parse errors are logged, not raised
- Unparseable files are recorded with `parse_error: true` in metadata
- Parser crashes are isolated per-file; do not abort indexing

### 3. Structural Graph Builder

**Purpose:** Build call graph, import graph, dependency graph, module graph.

**Graph Invariants:**
- Edges reference only symbol IDs that exist in `symbols.json`
- No dangling references (validated at index finalization)
- Graph is stored as adjacency list, not matrix (space-efficient)

### 4. Text Index (BM25)

**Engine:** Tantivy (primary), SQLite FTS (fallback)

**Interface Contract:**
```python
class LexicalIndex(Protocol):
    def index(self, documents: Iterator[Document]) -> None:
        """Indexes documents. Idempotent for same input."""
        ...
    
    def search(self, query: str, top_k: int) -> list[SearchResult]:
        """Returns ranked results. Deterministic for same query."""
        ...
```

### 5. Vector Index (Semantic Search)

**Engine:** LanceDB (primary), FAISS (fallback)

**Embedding Model:** Qwen3-Embedding-0.6B (offline, local inference)

**Embedding Contract:**
```python
class Embedder(Protocol):
    def embed_code(self, code: str) -> Vector:
        """Embeds code chunk. NO instruction prefix."""
        ...
    
    def embed_query(self, query: str) -> Vector:
        """Embeds query WITH instruction prefix (asymmetric)."""
        ...
    
    @property
    def dimension(self) -> int:
        """Returns embedding dimension. MUST be consistent."""
        ...
```

**Properties:**
- **Model**: Qwen3-Embedding-0.6B (offline, local inference)
- **Dimension**: 1024
- Offline-only (no API calls)
- Deterministic (same input → same vector)
- Model-agnostic (swappable via config)
- Instruction‑aware (for query side), raw embedding (for indexing side)

**FORBIDDEN:** Embedding code with instruction prefixes. Code is embedded RAW.

### 6. Metadata Store

**Engine:** DuckDB

**Schema:**
```sql
CREATE TABLE files (
    file_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    language TEXT,
    content_hash TEXT NOT NULL,
    line_count INTEGER,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE symbols (
    symbol_id TEXT PRIMARY KEY,
    file_id TEXT REFERENCES files(file_id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    signature TEXT,
    INDEX idx_symbols_name (name)
);

CREATE TABLE call_edges (
    caller_id TEXT REFERENCES symbols(symbol_id),
    callee_id TEXT REFERENCES symbols(symbol_id),
    call_site_line INTEGER,
    PRIMARY KEY (caller_id, callee_id, call_site_line)
);

CREATE TABLE index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Required keys: 'version', 'created_at', 'repo_hash'
```

---

## Indexer Storage Architecture

| Data Type | Engine | Storage Mode | Replaceability |
|-----------|--------|--------------|----------------|
| Metadata / Graphs | DuckDB | Embedded columnar DB | Postgres, SQLite |
| Dense Vectors | LanceDB | Versioned vector files | FAISS, Qdrant, Milvus |
| Lexical Index | Tantivy | Inverted index files | Elastic, Vespa, SQLite FTS |
| Artifacts | Filesystem | Deterministic JSON | S3, GCS |

**Adapter Contract:**
```python
class StorageAdapter(Protocol):
    def read(self, key: str) -> bytes: ...
    def write(self, key: str, data: bytes) -> None: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
```

All engines are accessed ONLY through adapters. Direct engine imports outside adapter modules are FORBIDDEN.

---

## Indexer Safety Measures

### 1. Deterministic Indexing

**Guarantee:** Same repo state → same index artifacts (byte-for-byte where applicable, semantically equivalent otherwise)

**Implementation Requirements:**
- Sort all collections before serialization
- Use deterministic hash functions (not Python's `hash()`)
- Timestamp fields use repo commit time, not wall clock
- Random seeds are fixed and configurable

### 2. No Heuristics

**FORBIDDEN in Indexer:**
- Threshold-based filtering
- "Smart" chunking based on content analysis
- Importance scoring
- Any decision that cannot be expressed as config

### 3. Language Isolation

- Each language has its own parser instance
- Parser crash in one language does not affect others
- Language detection is file-extension based (configurable mapping)

### 4. Incremental Updates

**Contract:**
- Only files with changed `content_hash` are re-indexed
- Deleted files are removed from all indexes
- Re-indexing a subset produces same result as full re-index of those files

### 5. Schema Versioning

**Migration Contract:**
- Schema version stored in `index_metadata` table
- Backward-compatible changes: consumers handle gracefully
- Breaking changes: require explicit re-index command

---

## Indexer Forbidden Patterns

| Pattern | Why Forbidden | Detection |
|---------|---------------|-----------|
| Routing logic | Intelligence layer | grep for "route", "dispatch", "select_strategy" |
| Evaluation hooks | Pollutes core | grep for "judge", "score", "evaluate" |
| Agent patterns | Autonomy | grep for "loop", "retry", "autonomous" |
| LLM calls | API dependency | grep for "openai", "gemini", "anthropic" |
| Magic numbers | Tuning risk | All numeric constants must be in config |

---

## Indexer Guarantees Summary

| Guarantee | Verification Method |
|-----------|---------------------|
| Deterministic | Hash comparison of two runs |
| Incremental | File count comparison |
| Offline | Network mock; no calls |
| Model-agnostic | Swap embedder; same behavior |
| API-agnostic | No HTTP imports |
| Replaceable | Each adapter has integration test |
| Testable | 100% adapter coverage |
| Immutable outputs | Write-once semantics enforced |

---

This is the canonical foundation.  
No system change is allowed to violate this design.

**Core Properties:**
- Deterministic
- Replaceable
- Offline
- Model-agnostic
- API-agnostic
- Storage-agnostic
- Fully incremental
- Immune to overfitting
- Immune to orchestration creep

And most importantly:  
**It cannot collapse under future complexity.**

---

# RETRIEVAL LAYER (Phase 2)

## Purpose

Convert a user query into a small, coherent, highly-relevant set of code blocks to feed the generator.

## Retrieval Invariants

| ID | Invariant | Test |
|----|-----------|------|
| RET-001 | Same query + same index → same candidates | Determinism test |
| RET-002 | Never modifies index artifacts | Write permission denied |
| RET-003 | All thresholds in config, not code | grep for hardcoded numbers |
| RET-004 | BM25 and vector search are parallelizable | No shared mutable state |
| RET-005 | Expansion is capped and auditable | Max additions enforced in config |

## Retrieval Non-Goals

- MUST NOT perform LLM-based query rewriting (that's a separate, optional preprocessor)
- MUST NOT learn from past queries
- MUST NOT modify scoring based on repo identity
- MUST NOT contain fallback/retry logic (that's adapter responsibility)
- MUST NOT call generation or evaluation modules

## High-Level Flow

```
Query → Ingest → Intent Classify → Query Prep → [BM25 ∥ Vector] → Hybrid Merge → Expand → Precision Recovery → Output
```

**Contract**: Each step is a pure function. No side effects. No state mutation.

## Component Contracts

### Query Preparer

```python
class QueryPreparer(Protocol):
    def prepare(self, query: str, intent: Intent) -> PreparedQuery:
        """
        Returns:
            dense_query: Instruction-wrapped query for embedding
            lexical_terms: Extracted keywords for BM25
        """
        ...
```

**FORBIDDEN**: Modifying query based on repo-specific patterns.

### Hybrid Merger

```python
class HybridMerger(Protocol):
    def merge(
        self, 
        bm25_results: list[Candidate], 
        vector_results: list[Candidate],
        config: MergeConfig
    ) -> list[Candidate]:
        """
        Uses Reciprocal Rank Fusion or configurable fusion.
        All weights from config. No magic constants.
        """
        ...
```

**Config Requirements:**
```yaml
hybrid:
  method: rrf  # or "linear"
  rrf_k: 10    # RRF parameter
  bm25_weight: 0.5  # for linear fusion
  vector_weight: 0.5
```

### Structural Expander

```python
class StructuralExpander(Protocol):
    def expand(
        self,
        candidates: list[Candidate],
        query: str,
        callgraph: CallGraph,
        config: ExpandConfig
    ) -> list[Candidate]:
        """
        Adds structurally related candidates (decorators, callees).
        
        Invariants:
        - max_additions enforced from config
        - Only adds if semantic similarity > min_similarity (from config)
        - Provenance tracked for each addition
        """
        ...
```

**Failure Handling:**
- If callgraph unavailable: skip expansion, log warning, continue
- If similarity check fails: do not add candidate
- Never raise exceptions that abort retrieval

## Precision Recovery (Missing-Entity Detection)

**Purpose**: Find referenced-but-missing functions in top candidates.

**Contract:**
- Scans top N candidates for unresolved references
- Performs targeted name search (BM25 exact match first, semantic fallback)
- Max M additions (from config, default: 3)
- Requires high confidence (name match OR similarity > threshold)

**FORBIDDEN**: 
- Unbounded expansion
- Adding candidates without provenance marking

## Retrieval Failure Modes

| Failure | Handling | Fallback |
|---------|----------|----------|
| BM25 index unavailable | Log error, skip BM25 | Vector-only results |
| Vector index unavailable | Log error, skip vector | BM25-only results |
| Both unavailable | Return empty + error flag | Caller decides |
| Expansion timeout | Return unexpanded results | Log timing |
| Zero results | Return empty list | Valid state |

## Anti-Overfitting Controls

| Control | Implementation |
|---------|----------------|
| No hardcoded names | Pattern lists from config (default: empty) |
| Config-driven thresholds | All in YAML with env overrides |
| Audit mode | Log any pattern match usage |
| Deterministic fallback | If reranker fails, use hybrid scores |

---

# RANKING LAYER (Phase 3)

## Purpose

Produce a deterministic, high-quality ranked candidate list from hybrid retrieval. Pure scoring—no side effects.

## Ranking Invariants

| ID | Invariant | Test |
|----|-----------|------|
| RNK-001 | Same inputs → same ranking | Order comparison |
| RNK-002 | Does not modify candidates | Immutable input |
| RNK-003 | Does not call generation | No gen imports |
| RNK-004 | All weights in config | grep verification |
| RNK-005 | Reranker is optional/pluggable | Feature flag test |

## Ranking Non-Goals

- MUST NOT synthesize text (scoring only)
- MUST NOT call LLM for generation
- MUST NOT persist results (caller's responsibility)
- MUST NOT implement caching (adapter concern)
- MUST NOT use repo-specific rules

## Input/Output Contract

```python
@dataclass
class RankingInput:
    query: str
    candidates: list[Candidate]  # Immutable
    config: RankConfig

@dataclass  
class RankingOutput:
    ranked_candidates: list[Candidate]  # Sorted by final_score
    debug_traces: list[DebugTrace]  # Per-candidate scoring breakdown
    metadata: RankMetadata  # Latency, reranker_used, etc.
```

**Contract Guarantees:**
- Rankings MUST NOT modify underlying index artifacts
- Rankings MUST NOT call generation step
- Rankings MUST be idempotent for same inputs

## Scoring Pipeline

```
Candidates → Pre-filter → Feature Enrichment → Base Fusion → [Reranker] → Final Fusion → Dedup → Output
```

### Feature Enrichment

Compute per-candidate feature vector (no LLM):

| Feature | Source | Normalization |
|---------|--------|---------------|
| bm25_score | Retrieval | Per-query percentile |
| dense_score | Retrieval | Per-query percentile |
| name_match | String comparison | Binary or overlap ratio |
| is_entrypoint | Graph metadata | Binary |
| has_decorator | Graph metadata | Binary |
| callgraph_distance | BFS from seed | Inverse distance |

### Fusion Formula

```python
base_score = (
    config.w_bm25 * bm25_percentile +
    config.w_dense * dense_percentile +
    config.w_name * name_match_score
)

final_score = (
    config.w_base * base_score +
    config.w_rerank * rerank_score +  # 0 if reranker disabled
    config.w_struct * struct_bonus
)
```

**All weights from config. No hardcoded values.**

### Reranker Contract

```python
class Reranker(Protocol):
    def batch_score(self, query: str, documents: list[str]) -> list[float]:
        """
        Cross-encoder scoring. No text synthesis.
        
        Properties:
        - Deterministic
        - No hallucination (scores, not generates)
        - Batch-optimized
        """
        ...
    
    def healthcheck(self) -> bool: ...
```

**Failure Handling:**
- Reranker timeout: Skip rerank, use base_score only
- Reranker error: Log, continue with base_score
- Mark output with `reranker_unavailable: true`

## Debug Trace Contract

Every ranked candidate includes:

```json
{
  "candidate_id": "string",
  "base_score": 0.72,
  "rerank_score": 0.85,
  "struct_bonus": 0.05,
  "final_score": 0.80,
  "features": {
    "bm25_pct": 0.77,
    "dense_pct": 0.69,
    "name_match": 1
  },
  "provenance": ["expansion:decorator", "micro_retrieval"]
}
```

---

# CONTEXT ASSEMBLY (Phase 4)

## Purpose

Convert ranked candidates into token-budgeted, ordered context for generation. Single most influential stage for answer quality.

## Context Assembly Invariants

| ID | Invariant | Test |
|----|-----------|------|
| CTX-001 | Same inputs + config → same context artifact | Hash comparison |
| CTX-002 | Token budget is strict upper bound | Count verification |
| CTX-003 | Provenance for every included block | All blocks have file/line |
| CTX-004 | No hardcoded structural rules | Config-driven tags |
| CTX-005 | Deterministic block ordering | Order comparison |

## Context Assembly Non-Goals

- MUST NOT call LLM for scoring (summarization is separate, gated)
- MUST NOT modify ranking scores
- MUST NOT embed model-specific token limits in code
- MUST NOT implement retry logic
- MUST NOT use repo-specific patterns unless explicitly configured

## Pipeline

```
Ranked Candidates → Enrich → Missing-Ref Detect → Score → Dedup → Budget → Compress → Order → Stitch → Output
```

### Block Scorer Signals

| Signal | Description | Source |
|--------|-------------|--------|
| semantic_score | Reranker score | Ranking layer |
| name_score | Identifier overlap | String matching |
| structural_priority | Entrypoint/decorator weight | Config-driven |
| novelty_score | Difference from selected | Cosine similarity |
| coherence_score | Fit with current context | Embedding comparison |

### Budget Manager Contract

```python
class BudgetManager(Protocol):
    def allocate(
        self,
        blocks: list[ScoredBlock],
        query_features: QueryFeatures,
        config: BudgetConfig
    ) -> list[AllocatedBlock]:
        """
        Assigns token budgets per block.
        
        Guarantees:
        - sum(allocated_tokens) <= config.max_tokens
        - Structural blocks prioritized
        - Uses same tokenizer as generation model
        """
        ...
```

**Tokenizer Contract:**
- Tokenizer is injected, not hardcoded
- Token counts are exact, not estimated
- Model changes require tokenizer swap

### Ordering Contract

Final context order (deterministic, configurable):

1. Query brief (one-line restatement)
2. Structural blocks (decorators, entrypoints) in call-order
3. Core implementation (functions, classes) by priority
4. Helper functions
5. Peripheral (tests, configs, summaries)
6. Provenance appendix

### Stitching Format

```
--- File: auth.py (lines 45-78) Symbol: require_admin ---
@decorator
def require_admin(func):
    ...

--- File: routes.py (lines 102-145) Symbol: delete_user ---
def delete_user(user_id: int):
    ...
```

## Context Output Contract

```python
@dataclass
class ContextArtifact:
    query_id: str
    context_text: str  # Stitched content
    blocks: list[BlockMetadata]  # id, file, start, end, tokens
    token_budget: int
    used_tokens: int
    provenance: dict  # Full trace
    explain_trace: list[str]  # Selection rationale
```

**Immutable**: Generation layer MUST NOT modify this artifact.

## Safety Measures

| Measure | Implementation |
|---------|----------------|
| No hardcoded structural rules | Tags from `PatternLearner` or config |
| Distribution-based calibration | Percentiles, not constants |
| Conservative micro-retrieval | Max M additions, high confidence only |
| Summarizer gating | LLM summarization opt-in, budgeted |
| Provenance tracking | Every token maps to source |
| Determinism | Same input+config = identical output |

## Failure Modes

| Failure | Handling | Output |
|---------|----------|--------|
| Zero candidates | Return empty context + flag | Valid state |
| Budget exceeded | Truncate lowest-priority blocks | Log truncation |
| Summarizer timeout | Skip summarization, use full blocks | Log fallback |
| Tokenizer mismatch | Raise error (do not guess) | Fail fast |

---

# GENERATION PHASE (Phase 5)

## Purpose

Final product-facing stage. Consumes curated context; produces human-facing answers. This is a thin adapter layer—not a decision engine.

## Generation Invariants

| ID | Invariant | Test |
|----|-----------|------|
| GEN-001 | Same context + same model + same config → same output (modulo model non-determinism) | Seed verification |
| GEN-002 | Does not modify context artifact | Immutable input |
| GEN-003 | Provider is pluggable | Swap providers; same interface |
| GEN-004 | No retrieval or ranking logic | No retrieval imports |
| GEN-005 | Raw response always persisted before parsing | Artifact ordering |

## Generation Non-Goals

- MUST NOT contain retrieval logic
- MUST NOT implement ranking or scoring
- MUST NOT learn from responses
- MUST NOT auto-retry on content failures (infrastructure retries only)
- MUST NOT modify context based on generation results

## Provider Contract

```python
class ProviderConnector(Protocol):
    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        ...
    
    def invoke_stream(self, request: ProviderRequest, on_chunk: Callable) -> ProviderResponse:
        """Streaming invocation."""
        ...
    
    def healthcheck(self) -> bool: ...
    
    def capabilities(self) -> ProviderCapabilities:
        """Returns: streaming, max_tokens, rate_limits, etc."""
        ...
```

**Implementations Required:**
- `LocalProvider` (ollama/vLLM)
- `OpenAIProvider`
- `GeminiProvider`
- `GenericHTTPProvider`

## Request/Response Contract

```python
@dataclass
class GenerationRequest:
    request_id: str
    query: str
    intent: Intent
    context_blocks: list[ContextBlock]
    prompt_template: str
    template_variables: dict
    output_mode: Literal["TEXT", "STRUCTURED", "TRACE", "EXAMPLE"]
    model_config: ModelConfig  # temperature, max_tokens, etc.
    
@dataclass
class GenerationResult:
    request_id: str
    status: Literal["OK", "PARTIAL", "ERROR"]
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    raw_text: str  # ALWAYS persisted before parsing
    parsed_output: Optional[dict]
    diagnostics: Diagnostics  # parse_warnings, hallucination_flags
```

## Prompting Contract

**Separation of Concerns:**
- Template = instruction scaffold (stored in YAML, versioned)
- Context = factual code snippets (from Context Assembly)
- Never mix the two in code

**FORBIDDEN in Templates:**
- Repo-specific examples (function names, file paths from test repos)
- Hardcoded thresholds or magic numbers
- Model-specific syntax (unless in model-specific template variant)

## JSON Parsing Resilience

1. Always store `raw_text` BEFORE any parsing attempt
2. Use tolerant parser (strip fences, fix trailing commas)
3. Log every correction applied
4. If parse fails: set `parsed_output=null`, tag `parse_failure=true`
5. Never silently accept malformed output

## Hallucination Mitigation

| Strategy | Implementation |
|----------|----------------|
| Evidence request | Prompt: "For each claim, cite file:line OR 'NOT_IN_CONTEXT'" |
| Cross-check | Compare claimed identifiers against context snapshot |
| Conservative mode | For high-risk queries, require exact implementation presence |
| Flag generation | Set `hallucination_flags` when claims not found in context |

## Failure Modes

| Failure | Handling | Output |
|---------|----------|--------|
| Provider timeout | Retry once with backoff, then error | `status: ERROR` |
| Parse failure | Store raw, flag for review | `parse_failure: true` |
| Stream interruption | Buffer last chunk, mark interrupted | `stream_interrupted` |
| Empty response | Log, return empty with flag | Valid state |

---

# EVALUATION FRAMEWORK

## Purpose

Completely isolated from core pipeline. Provides reproducible experiments, metrics, and judge capability.

## Evaluation Invariants

| ID | Invariant | Test |
|----|-----------|------|
| EVAL-001 | Zero imports from core pipeline | Import graph analysis |
| EVAL-002 | Reads only immutable artifacts | No write access to index |
| EVAL-003 | Judge prompts contain no repo identifiers | Template scan |
| EVAL-004 | Same run config → reproducible results | Hash comparison |

## Evaluation Non-Goals

- MUST NOT influence retrieval or ranking scores
- MUST NOT modify index artifacts
- MUST NOT provide feedback loops to core pipeline
- MUST NOT contain production routing logic

## Data Model (DuckDB)

```sql
-- Experiments
CREATE TABLE experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    config_blob JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual runs
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT REFERENCES experiments,
    query_text TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms INTEGER,
    status TEXT,
    artifact_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Judge scores
CREATE TABLE judge_scores (
    run_id TEXT REFERENCES runs,
    metric TEXT NOT NULL,
    value REAL,
    judge_model TEXT,
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, metric)
);
```

## Judge Contract

```python
class Judge(Protocol):
    def score(self, run_artifact: RunArtifact) -> JudgeResult:
        """
        Scores based on context_snapshot only.
        
        Metrics returned:
        - semantic_correctness (0-10)
        - factual_accuracy (0-10)
        - completeness (0-10)
        - hallucination_rate (0-1)
        """
        ...
```

**FORBIDDEN in Judge Prompts:**
- Test repo identifiers
- External knowledge references
- Hardcoded "correct" answers

---

# FORBIDDEN PATTERNS (Global)

These patterns are FORBIDDEN across all layers. Detection methods are provided.

| Pattern | Why Forbidden | Detection |
|---------|---------------|-----------|
| Agents / autonomous loops | Non-determinism, debugging complexity | grep: "while.*retry", "autonomous", "agent" |
| Orchestration logic | Intelligence layer | grep: "router", "dispatch", "select_strategy" |
| Evaluation in core | Feedback loops | Import analysis: eval in retrieval/ranking/context |
| Hardcoded thresholds | Overfitting risk | grep: numeric literals outside config |
| Repo-specific patterns | Overfitting | grep: known test repo names |
| Cross-layer imports | Module boundary violation | Import graph analysis |
| Hidden control flow | Non-determinism | grep: random, time-based conditionals |
| Magic routing | Intelligence layer | grep: "if.*query.*contains" |
| Learning from feedback | Feedback loops | No ML training in runtime |
| Retry with backoff in core | Orchestration | Retries only in adapters |

## Violation Response

1. Automated detection runs in CI
2. Violations block merge
3. Each violation requires explicit exception with justification
4. Exceptions are logged and regularly audited

---

# TESTING IMPLICATIONS

## Required Test Categories

| Category | Scope | Frequency |
|----------|-------|-----------|
| Determinism tests | Each layer | Every PR |
| Import boundary tests | Cross-layer | Every PR |
| Adapter swap tests | Storage/Provider | Weekly |
| Regression tests | Full pipeline | Daily |
| Performance tests | Latency/tokens | Weekly |
| Overfitting detection | Pattern scan | Every PR |

## Determinism Test Pattern

```python
def test_determinism(layer):
    result1 = layer.process(fixed_input, fixed_config)
    result2 = layer.process(fixed_input, fixed_config)
    assert result1 == result2  # Byte-equal or semantic-equal
```

## Import Boundary Test Pattern

```python
def test_no_upward_imports():
    for module in ["retrieval", "ranking", "context", "generation"]:
        imports = get_imports(f"homllm/{module}")
        for imp in imports:
            assert not imp.startswith("homllm.evaluation")
            assert direction_is_valid(module, imp)
```

---

# OBSERVABILITY CONTRACT

## Required Metrics (per layer)

| Layer | Metrics |
|-------|---------|
| Indexer | files_indexed, symbols_extracted, index_time_ms |
| Retrieval | candidates_returned, bm25_time_ms, vector_time_ms |
| Ranking | rerank_time_ms, reranker_used, cache_hit_rate |
| Context | blocks_selected, tokens_used, budget_utilization |
| Generation | tokens_in, tokens_out, latency_ms, provider, parse_success |

## Structured Logging Contract

Every log entry MUST include:

```json
{
  "timestamp": "ISO8601",
  "level": "INFO|WARN|ERROR",
  "layer": "indexer|retrieval|ranking|context|generation",
  "request_id": "uuid",
  "message": "string",
  "metadata": {}
}
```

## Tracing Contract

- All requests have a unique `request_id` (UUID)
- `request_id` propagates through all layers
- Artifacts are keyed by `request_id`
- Traces are exportable (OpenTelemetry compatible)

---

# APPENDIX: Configuration Schema

All tunable values MUST be in config, not code.

```yaml
# Default configuration schema
indexer:
  languages: ["python", "javascript", "typescript"]
  ignore_patterns: [".git", "node_modules", "__pycache__"]
  chunk_max_lines: 100

retrieval:
  bm25:
    engine: tantivy
    top_k: 50
  vector:
    engine: lancedb
    top_k: 50
  hybrid:
    method: rrf
    rrf_k: 10
  expansion:
    enabled: true
    max_additions: 4
    min_similarity: 0.25

ranking:
  reranker:
    enabled: true
    model: "Qwen3-Reranker-0.6B"  # Offline, local inference
    top_m: 40
  weights:
    w_base: 0.4
    w_rerank: 0.55
    w_struct: 0.05

context:
  max_tokens: 4000
  budget_mode: adaptive
  summarization_enabled: false
  ordering: "structural_first"

generation:
  default_provider: gemini
  default_model: gemini-2.5-flash
  temperature: 0.0
  max_output_tokens: 2000

evaluation:
  judge_model: gemma-3-27b-it
  metrics: ["semantic_correctness", "factual_accuracy", "completeness"]
  artifact_retention_days: 90
```

---

# DOCUMENT CHANGELOG

| Version | Date | Changes |
|---------|------|---------|
| 2.1 | Original | Initial canonical architecture |
| 2.2 | Refined | Added: Invariant tables, Non-Goals, Failure modes, Testing implications, Observability contract, Forbidden patterns, Configuration schema, Explicit contracts for all interfaces |

---

**END OF CANONICAL ARCHITECTURE DOCUMENT**

This document is immutable in spirit.  
Refinements strengthen constraints.  
Changes that weaken guarantees require explicit justification and audit.

---

## REPOSITORY ROOT

```
homllm/
├── src/                        # Core engine (headless, pure)
│   └── homllm/
│       ├── __init__.py
│       ├── common/             # Shared types ONLY (no logic)
│       │   ├── types.py
│       │   ├── config.py
│       │   └── exceptions.py
│       │
│       ├── indexer/            # Phase 1 (FROZEN CORE)
│       │   ├── __init__.py
│       │   ├── interfaces.py
│       │   ├── pipeline.py
│       │   ├── scanner.py
│       │   ├── parser.py
│       │   ├── graph_builder.py
│       │   └── storage/
│       │       ├── __init__.py
│       │       ├── duckdb_adapter.py
│       │       ├── tantivy_adapter.py
│       │       ├── lancedb_adapter.py
│       │       └── filesystem_adapter.py
│       │
│       ├── retrieval/          # Phase 2
│       │   ├── __init__.py
│       │   ├── interfaces.py
│       │   ├── preparer.py
│       │   ├── bm25.py
│       │   ├── vector.py
│       │   ├── hybrid.py
│       │   └── expander.py
│       │
│       ├── ranking/            # Phase 3
│       │   ├── __init__.py
│       │   ├── interfaces.py
│       │   ├── features.py
│       │   ├── fusion.py
│       │   └── reranker.py
│       │
│       ├── context/            # Phase 4
│       │   ├── __init__.py
│       │   ├── interfaces.py
│       │   ├── assembler.py
│       │   ├── scorer.py
│       │   ├── deduper.py
│       │   ├── budget.py
│       │   └── stitcher.py
│       │
│       ├── generation/         # Phase 5 (ADAPTER ONLY)
│       │   ├── __init__.py
│       │   ├── interfaces.py
│       │   ├── adapter.py
│       │   ├── providers/
│       │   │   ├── local.py
│       │   │   ├── openai.py
│       │   │   ├── gemini.py
│       │   │   └── generic_http.py
│       │   └── templates/
│       │       └── explain.yaml
│       │
│       └── storage/            # Shared storage abstractions
│           ├── __init__.py
│           ├── base.py
│           └── adapters/
│
├── cli/                        # PRIMARY INTERFACE
│   ├── __init__.py
│   └── main.py                 # query, index, inspect, replay
│
├── evaluation/                 # ISOLATED SYSTEM
│   ├── __init__.py
│   ├── runner.py
│   ├── judge.py
│   ├── metrics.py
│   ├── storage.py
│   └── experiments/
│
├── configs/                    # ALL CONFIGURATION
│   ├── default.yaml
│   ├── indexer.yaml
│   ├── retrieval.yaml
│   ├── ranking.yaml
│   ├── context.yaml
│   └── generation.yaml
│
├── artifacts/                  # IMMUTABLE OUTPUTS
│   └── runs/
│
├── indexes/                    # PER‑REPO INDEXES (gitignored)
│
├── tests/                      # STRICTLY MIRROR src/
│   ├── unit/
│   ├── integration/
│   └── determinism/
│
├── pyproject.toml
├── README.md
└── .gitignore
```

---