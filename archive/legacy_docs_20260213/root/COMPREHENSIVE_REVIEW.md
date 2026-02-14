# Comprehensive Architecture Review - All Phases

## Review Methodology

This review systematically checks each phase against the architecture document for:
1. **Completeness**: All required components present
2. **Correctness**: Implementation matches architecture contracts
3. **Invariant Compliance**: All invariants satisfied
4. **Non-Goal Compliance**: No forbidden patterns
5. **Missing Functionality**: TODOs and incomplete implementations

---

## Phase 1: Indexer - Review

### Required Components Checklist

- [x] File Scanner (`scanner.py`) - ✅ Implemented
- [x] Code Parser (`parser.py`) - ✅ Implemented (Tree-Sitter)
- [x] Graph Builder (`graph_builder.py`) - ✅ Implemented
- [x] BM25 Index (`storage/tantivy_adapter.py`) - ✅ Implemented
- [x] Vector Index (`storage/lancedb_adapter.py`) - ✅ Implemented
- [x] Embedder (`embedder.py`) - ✅ Implemented (Qwen)
- [x] Metadata Store (`storage/duckdb_adapter.py`) - ✅ Implemented
- [x] Filesystem Adapter (`storage/filesystem_adapter.py`) - ✅ Implemented
- [x] Pipeline (`pipeline.py`) - ✅ Implemented

### Artifact Generation Checklist

- [x] `symbols.json` - ✅ Written with version field
- [x] `files.json` - ✅ Written with version field
- [x] `callgraph.json` - ✅ Written with version field
- [x] `dependencies.json` - ⚠️ Written but empty (placeholder)

### Critical Issues Found

#### 1. **Dependencies.json is Empty** ⚠️
- **Status**: Placeholder implementation
- **Architecture Requirement**: Import/export relationships
- **Impact**: Medium - Import graph not extracted
- **Fix Required**: Implement import/export extraction in parser

#### 2. **Incremental Indexing Not Fully Implemented** ⚠️
- **Status**: Parameter exists but logic incomplete
- **Architecture Requirement**: IDX-003 - Only changed files re-indexed
- **Impact**: Medium - Full re-index always performed
- **Fix Required**: Implement content_hash comparison logic

#### 3. **DuckDB Connection Initialized** ✅
- **Status**: Actually implemented in pipeline (lines 86-87)
- **Note**: TODO comment in adapter is outdated, connection is properly initialized

#### 4. **Content Loading Missing in Retrievers** ❌
- **Status**: BM25/Vector retrievers return empty content
- **Architecture Requirement**: Candidates need actual code content
- **Impact**: High - Retrieval returns empty candidates
- **Fix Required**: Load content from index or metadata store

### Invariant Compliance

- [x] IDX-001: Deterministic artifacts - ✅ Sorted outputs, deterministic hashing
- [x] IDX-002: No network calls - ✅ Verified (no HTTP imports)
- [ ] IDX-003: Incremental indexing - ⚠️ Logic incomplete
- [x] IDX-004: Language isolation - ✅ Per-file error handling

### Non-Goal Compliance

- [x] No query routing - ✅ Verified
- [x] No embedding APIs - ✅ Local model only
- [x] No evaluation imports - ✅ Verified
- [x] No retry logic - ✅ Verified
- [x] No caching in indexer - ✅ Verified

---

## Phase 2: Retrieval - Review

### Required Components Checklist

- [x] Query Preparer (`preparer.py`) - ✅ Implemented
- [x] BM25 Retriever (`bm25.py`) - ⚠️ Missing content loading
- [x] Vector Retriever (`vector.py`) - ⚠️ Missing content loading
- [x] Hybrid Merger (`hybrid.py`) - ✅ Implemented (RRF + Linear)
- [x] Structural Expander (`expander.py`) - ⚠️ Similarity check incomplete
- [x] Precision Recovery (`precision_recovery.py`) - ⚠️ Mostly placeholder
- [x] Pipeline (`pipeline.py`) - ✅ Implemented

### Critical Issues Found

#### 1. **Content Loading Missing** ❌
- **Status**: Both retrievers return `content=""`
- **Architecture Requirement**: Candidates must have actual code
- **Impact**: Critical - Retrieval unusable without content
- **Fix Required**: 
  - **LanceDB**: Modify `search()` to return content field (stored in table)
  - **BM25**: Load from DuckDB symbols table or re-read from filesystem using file_id + symbol_id

#### 2. **Structural Expander Similarity Check Missing** ❌
- **Status**: TODO comment, doesn't check `min_similarity`
- **Architecture Requirement**: "Only adds if semantic similarity > min_similarity"
- **Impact**: High - Expansion may add irrelevant candidates
- **Fix Required**: Implement similarity comparison using embedder

#### 3. **Precision Recovery Not Implemented** ❌
- **Status**: Mostly placeholder TODOs
- **Architecture Requirement**: "Scans top N candidates for unresolved references"
- **Impact**: Medium - Missing entity detection not working
- **Fix Required**: Implement reference extraction and targeted search

#### 4. **Callgraph Not Loaded** ❌
- **Status**: `callgraph = {}  # TODO: Load from callgraph.json`
- **Architecture Requirement**: Expander needs callgraph
- **Impact**: High - Structural expansion disabled
- **Fix Required**: Load from `callgraph.json` artifact

#### 5. **Intent Classifier Missing** ⚠️
- **Status**: Intent passed as parameter, not classified
- **Architecture Requirement**: Flow mentions "Intent Classify"
- **Impact**: Low - Can be external preprocessor
- **Note**: Acceptable if documented as external

### Invariant Compliance

- [x] RET-001: Deterministic candidates - ✅ Verified
- [x] RET-002: Never modifies artifacts - ✅ Read-only access
- [x] RET-003: All thresholds in config - ✅ Verified (after fixes)
- [x] RET-004: Parallelizable search - ✅ No shared state
- [x] RET-005: Expansion capped - ✅ Config-driven max

### Non-Goal Compliance

- [x] No LLM query rewriting - ✅ Verified
- [x] No learning from queries - ✅ Verified
- [x] No repo-specific scoring - ✅ Verified
- [x] No retry logic - ✅ Verified
- [x] No generation/evaluation imports - ✅ Verified

---

## Phase 3: Ranking - Review

### Required Components Checklist

- [x] Feature Enricher (`features.py`) - ✅ Implemented
- [x] Score Fusion (`fusion.py`) - ✅ Implemented (config-driven)
- [x] Reranker (`reranker.py`) - ✅ Implemented (Qwen)
- [x] Deduplicator (`dedup.py`) - ✅ Implemented
- [x] Pipeline (`pipeline.py`) - ✅ Implemented

### Critical Issues Found

#### 1. **Pre-filter Step Missing** ⚠️
- **Status**: Mentioned in flow but not implemented
- **Architecture Requirement**: "Candidates → Pre-filter → Feature Enrichment"
- **Impact**: Low - May be optional, but should verify
- **Note**: May be intentional (no filtering needed)

#### 2. **Callgraph Distance BFS Simplified** ⚠️
- **Status**: Simplified check, not true BFS
- **Architecture Requirement**: "callgraph_distance: BFS from seed"
- **Impact**: Low - Functional but not complete
- **Note**: Simplified version works for basic cases

### Invariant Compliance

- [x] RNK-001: Deterministic ranking - ✅ Verified
- [x] RNK-002: Immutable candidates - ✅ Verified
- [x] RNK-003: No generation imports - ✅ Verified
- [x] RNK-004: All weights in config - ✅ Fixed (struct bonuses)
- [x] RNK-005: Reranker pluggable - ✅ Verified

### Non-Goal Compliance

- [x] No text synthesis - ✅ Scoring only
- [x] No LLM generation - ✅ Verified
- [x] No result persistence - ✅ Verified
- [x] No caching - ✅ Verified
- [x] No repo-specific rules - ✅ Verified

---

## Phase 4: Context Assembly - Review

### Required Components Checklist

- [x] Block Assembler (`assembler.py`) - ✅ Implemented
- [x] Block Scorer (`scorer.py`) - ✅ Implemented (config-driven)
- [x] Deduplicator (`deduper.py`) - ✅ Implemented
- [x] Budget Manager (`budget.py`) - ✅ Implemented
- [x] Stitcher (`stitcher.py`) - ✅ Implemented
- [x] Pipeline (`pipeline.py`) - ✅ Implemented

### Critical Issues Found

#### 1. **Missing-Ref Detection Not Implemented** ❌
- **Status**: Mentioned in flow comment (line 26) but not in actual pipeline
- **Architecture Requirement**: "Ranked Candidates → Enrich → Missing-Ref Detect → Score"
- **Impact**: Medium - Missing reference detection skipped
- **Fix Required**: Add step between block assembly and scoring to detect unresolved references

#### 2. **Compress Step Missing** ❌
- **Status**: Mentioned in flow comment but not implemented
- **Architecture Requirement**: "Budget → Compress → Order → Stitch"
- **Impact**: Medium - No compression applied
- **Fix Required**: Add compression step after budget allocation (may be optional if not needed)

#### 3. **Provenance Appendix Omitted** ⚠️
- **Status**: Commented out in stitcher
- **Architecture Requirement**: "6. Provenance appendix"
- **Impact**: Low - Optional per architecture
- **Note**: Can be added later if needed

### Additional Issues Found

#### 3. **Hardcoded Structural Priority Values** ⚠️
- **Status**: Values (0.3, 0.2, 0.5) hardcoded in `_compute_structural_priority()`
- **Architecture Requirement**: CTX-004 - All thresholds in config
- **Impact**: Medium - Should use config values
- **Fix Required**: Use `config.structural_priority_entrypoint_bonus`, etc.

#### 4. **Hardcoded Coherence Values** ⚠️
- **Status**: Values (0.8, 0.5) hardcoded in `_compute_coherence_score()`
- **Architecture Requirement**: CTX-004 - All thresholds in config
- **Impact**: Medium - Should use config values
- **Fix Required**: Use `config.coherence_same_file_bonus`, `coherence_different_file_bonus`

#### 5. **Scorer Config Not Passed** ⚠️
- **Status**: Pipeline passes config but scorer `__init__` doesn't accept it
- **Impact**: Low - Config exists but not used in scorer
- **Fix Required**: Update scorer `__init__` to accept and store config

### Invariant Compliance

- [x] CTX-001: Deterministic context - ✅ Verified
- [x] CTX-002: Token budget strict - ✅ Verified
- [x] CTX-003: Provenance tracked - ✅ Verified
- [ ] CTX-004: No hardcoded rules - ⚠️ Some hardcoded values remain (structural, coherence)
- [x] CTX-005: Deterministic ordering - ✅ Verified

### Non-Goal Compliance

- [x] No LLM scoring - ✅ Verified
- [x] No ranking score modification - ✅ Verified
- [x] No model-specific limits - ✅ Tokenizer injected
- [x] No retry logic - ✅ Verified
- [x] No repo-specific patterns - ✅ Verified

---

## Phase 5: Generation - Review

### Required Components Checklist

- [x] Provider Interfaces (`interfaces.py`) - ✅ Complete
- [x] LocalProvider (`providers/local.py`) - ✅ Implemented
- [x] OpenAIProvider (`providers/openai.py`) - ✅ Implemented
- [x] GeminiProvider (`providers/gemini.py`) - ✅ Implemented
- [x] GenericHTTPProvider (`providers/generic_http.py`) - ✅ Implemented
- [x] Template Loader (`template_loader.py`) - ✅ Implemented
- [x] JSON Parser (`parser.py`) - ✅ Implemented (resilient)
- [x] Hallucination Detector (`hallucination.py`) - ✅ Implemented
- [x] Generation Adapter (`adapter.py`) - ✅ Implemented

### Critical Issues Found

#### 1. **Model Selection Hardcoded** ⚠️
- **Status**: Fallback default in adapter
- **Architecture Requirement**: Should come from GenerationConfig
- **Impact**: Low - Works but not config-driven
- **Fix Required**: Use `GenerationConfig.default_model`

#### 2. **Provider Request Model Field** ⚠️
- **Status**: Model should come from request, not adapter
- **Architecture Requirement**: Model in GenerationRequest
- **Impact**: Low - Functional but not ideal
- **Note**: GenerationRequest doesn't have model field currently

### Invariant Compliance

- [x] GEN-001: Deterministic (modulo model) - ✅ Verified
- [x] GEN-002: Context immutable - ✅ Verified (tests)
- [x] GEN-003: Provider pluggable - ✅ Verified
- [x] GEN-004: No retrieval/ranking - ✅ Verified
- [x] GEN-005: Raw text persisted - ✅ Enforced in code

### Non-Goal Compliance

- [x] No retrieval logic - ✅ Verified
- [x] No ranking/scoring - ✅ Verified
- [x] No learning - ✅ Verified
- [x] No auto-retry - ✅ Verified
- [x] No context modification - ✅ Verified

---

## Summary: Critical Issues by Priority

### 🔴 CRITICAL (Must Fix Before Production)

1. **Content Loading in Retrievers** (Phase 2)
   - BM25 and Vector retrievers return empty content
   - Blocks retrieval from working
   - **Fix**: Load content from LanceDB metadata or DuckDB

2. **DuckDB Connection Not Initialized** (Phase 1)
   - Schema not created, operations will fail
   - **Fix**: Call `connect()` and `initialize_schema()` in pipeline

3. **Callgraph Not Loaded** (Phase 2)
   - Structural expansion disabled
   - **Fix**: Load from `callgraph.json` in retrieval pipeline

### 🟡 HIGH (Should Fix Soon)

4. **Structural Expander Similarity Check** (Phase 2)
   - Doesn't enforce `min_similarity` threshold
   - **Fix**: Implement similarity comparison

5. **Missing-Ref Detection** (Phase 4)
   - Step mentioned in flow but not implemented
   - **Fix**: Implement reference extraction and search

6. **Dependencies.json Empty** (Phase 1)
   - Import/export graph not extracted
   - **Fix**: Extract import relationships in parser

7. **Hardcoded Values in Context Scorer** (Phase 4)
   - Structural priority and coherence bonuses hardcoded
   - **Fix**: Use config values (already in ContextConfig)

### 🟢 MEDIUM (Can Fix Later)

7. **Precision Recovery** (Phase 2)
   - Mostly placeholder, needs implementation
   - **Fix**: Implement reference extraction from code

8. **Incremental Indexing** (Phase 1)
   - Logic incomplete, always full re-index
   - **Fix**: Implement content_hash comparison

9. **Compress Step** (Phase 4)
   - Mentioned but not implemented
   - **Fix**: Add compression if needed

### 🔵 LOW (Nice to Have)

10. **Pre-filter in Ranking** (Phase 3)
    - May be optional, verify with architecture

11. **BFS for Callgraph Distance** (Phase 3)
    - Simplified version works

12. **Provenance Appendix** (Phase 4)
    - Optional per architecture

---

## Architecture Compliance Score

| Phase | Components | Invariants | Non-Goals | Overall |
|-------|-----------|------------|-----------|---------|
| Phase 1 (Indexer) | 9/9 ✅ | 3/4 ⚠️ | 5/5 ✅ | 85% |
| Phase 2 (Retrieval) | 7/7 ✅ | 5/5 ✅ | 5/5 ✅ | 70%* |
| Phase 3 (Ranking) | 5/5 ✅ | 5/5 ✅ | 5/5 ✅ | 95% |
| Phase 4 (Context) | 6/6 ✅ | 4/5 ⚠️ | 5/5 ✅ | 80% |
| Phase 5 (Generation) | 9/9 ✅ | 5/5 ✅ | 5/5 ✅ | 95% |

*Phase 2 score lowered due to missing content loading (critical)

---

## Next Steps

1. **Fix Critical Issues** (Priority 1)
   - Content loading in retrievers
   - DuckDB initialization
   - Callgraph loading

2. **Fix High Priority Issues** (Priority 2)
   - Similarity check in expander
   - Missing-ref detection
   - Dependencies extraction

3. **Complete Medium Priority** (Priority 3)
   - Precision recovery
   - Incremental indexing
   - Compression step

4. **Verify and Test** (Priority 4)
   - Run full pipeline integration tests
   - Verify all invariants
   - Check determinism end-to-end
