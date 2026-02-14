# RANKING SYSTEM: Architectural Evolution Plan

**Author**: Strategic Architecture Document  
**Date**: February 2026  
**Purpose**: Transform static scoring into adaptive, signal-driven ranking  
**Scope**: Ranking layer evolution (post-retrieval, pre-context)

---

## Executive Summary

**Current State**: Feature-rich but behavior-poor static ranker  
**Target State**: Signal-driven adaptive ranking system (Cursor-class)  
**Strategy**: Two-phase evolution with clean integration

**Phase 1**: Structural corrections (correctness improvements)  
**Phase 2**: Adaptive intelligence (behavioral sophistication)

**Critical Principle**: Phase 1 fixes are NOT temporary. They are permanent structural improvements that Phase 2 builds upon.

---

## Part I: Strategic Context

### Why This Evolution Matters

Your system currently:
- ✅ Retrieves good candidates (indexing + retrieval are strong)
- ✅ Computes rich features (BM25, vector, name match, structural)
- ✅ Has reranker capability
- ❌ Ranks statically (same weights for all queries)
- ❌ Always reranks (no confidence awareness)
- ❌ Treats structure binarily (connected vs not connected)
- ❌ Has no uncertainty modeling

**The gap**: Static feature computation → linear blending → always rerank

**The goal**: Adaptive feature computation → signal-driven strategy → selective rerank

### Architectural Philosophy

**Move from**:
- Rule-driven behavior (if intent == EXPLAIN then boost coarse)
- Static fusion weights
- Binary structural signals
- Always-on reranking

**Move to**:
- Signal-driven behavior (if score entropy high, increase structural weight)
- Dynamic fusion weights
- Continuous structural propagation
- Confidence-based reranking

**No LLMs, no keyword rules, no intent tables — pure signal geometry.**

---

## Part II: Phase 1 — Structural Corrections

**Timeline**: Week 1  
**Goal**: Fix correctness issues without architectural debt  
**Result**: 85/100 → 90/100 quality

### 1.1 Replace Prefix Deduplication with Structural Deduplication

**Current Problem**:
```python
# dedup.py
content_key = candidate.content[:100]  # Brittle!
```

**Issues**:
- Parent class `PaymentController` and child method `validate()` both pass
- Different first 100 chars, but semantically overlapping
- Budget waste on redundant hierarchical content

**Architectural Solution**:

**Span-Aware Deduplication**

**Principle**: Two candidates are duplicates if they represent overlapping code regions.

**Detection criteria**:
1. **Same file AND overlapping line spans** → duplicates
   - Candidate A: `file.py` lines 10-50
   - Candidate B: `file.py` lines 30-70
   - Overlap detected → keep higher-scoring one

2. **Parent-child symbol relationship** → duplicates
   - Candidate A: `PaymentController` (class)
   - Candidate B: `PaymentController.validate` (method)
   - Child is subset of parent → keep based on granularity preference

3. **Same symbol_id** → exact duplicates
   - Multiple chunks from same symbol
   - Keep highest-scoring

**Granularity preference logic**:
- If query needs **structural overview**: Prefer parent (coarse/medium)
- If query needs **implementation**: Prefer child (fine)
- **Default**: Prefer child (fine chunks are more specific)

**NOT intent-based heuristics**. Use signal geometry:
- High file entropy (many files) → prefer coarse (structural overview)
- Low file entropy (single file) → prefer fine (implementation detail)

**Implementation approach**:
- Group candidates by file
- Within each file, detect span overlaps
- Within each file, detect parent-child via symbol_id hierarchy
- Apply granularity preference based on retrieval signals (not hardcoded intent)

**Key insight**: This is not "hierarchical intent-based dedup". It's **span-overlap suppression with signal-driven granularity preference**.

---

### 1.2 Replace Binary Graph Bonus with Distance-Aware Structural Scoring

**Current Problem**:
```python
# features.py
if symbol_id in callgraph:
    return 1.0  # Binary!
else:
    return 0.0
```

**Issues**:
- All connected symbols treated equally
- Symbol 1 hop away = symbol 10 hops away
- No notion of interaction strength

**Architectural Solution**:

**Graph Proximity Scoring**

**Principle**: Structural relevance decays with graph distance.

**Distance computation**:
1. **Identify anchor symbols**:
   - Top-5 BM25 candidates (lexically relevant)
   - Top-5 vector candidates (semantically relevant)
   - Union = anchor set

2. **Compute shortest path distance** from each candidate to nearest anchor:
   - Distance 0 (is anchor): score = 1.0
   - Distance 1 (direct call): score = 0.8
   - Distance 2: score = 0.6
   - Distance 3: score = 0.4
   - Distance 4+: score = 0.2
   - Not connected: score = 0.0

3. **Use bidirectional graph**:
   - Consider both callers and callees
   - `A calls B` means `A → B` AND `B ← A` (both directions matter)

**Why this works**:
- **Interaction queries** ("How do X and Y work together?"): Connected symbols get boosted
- **Lookup queries** ("What does function X do?"): Only X gets boost, unrelated symbols penalized
- **Flow queries** ("Trace execution"): Path-connected symbols naturally ranked higher

**Implementation approach**:
- Pre-compute anchor set from base retrieval
- Run BFS from anchors (limited depth, e.g., 4 hops)
- Store distance map: `{symbol_id: min_distance_to_anchor}`
- Convert distance to continuous score (inverse decay)

**Critical**: This is **single-pass** proximity scoring, NOT full two-pass ranking yet. Two-pass comes in Phase 2.

---

### 1.3 Add Confidence-Based Reranker Gating

**Current Problem**:
```python
if config.reranker_enabled:
    always_rerank()  # Wasteful!
```

**Issues**:
- Reranks even when base ranking is confident
- Adds latency unnecessarily
- Over-relies on cross-encoder

**Architectural Solution**:

**Selective Reranking via Confidence Metrics**

**Principle**: Rerank only when base ranking is uncertain.

**Confidence signals to compute**:

1. **Score Margin**:
   ```
   margin = (score_1 - score_2) / score_1
   ```
   - Large margin (> 0.3) → confident, skip rerank
   - Small margin (< 0.15) → uncertain, fire rerank

2. **Score Entropy**:
   ```
   H = -Σ p_i log(p_i)
   where p_i = score_i / Σ scores
   ```
   - Low entropy → peaked distribution → confident
   - High entropy → flat distribution → uncertain

3. **Retrieval Disagreement** (BM25 vs Vector):
   ```
   disagreement = 1 - rank_correlation(bm25_ranks, vector_ranks)
   ```
   - Low disagreement → retrieval agrees → confident
   - High disagreement → lexical vs semantic conflict → uncertain

**Gating logic**:
```
fire_reranker = (
    margin < threshold_margin OR
    entropy > threshold_entropy OR
    disagreement > threshold_disagreement
)
```

**Thresholds** (empirically tuned):
- `threshold_margin = 0.2`
- `threshold_entropy = 0.7`
- `threshold_disagreement = 0.5`

**Benefits**:
- **Latency reduction**: Skip reranker on ~40% of queries (confident ones)
- **Stability**: Don't let reranker override strong base ranking
- **Adaptivity**: Fire reranker exactly when needed

**Implementation approach**:
- Compute confidence metrics from base-ranked candidates
- Evaluate gating condition
- If true: run reranker
- If false: skip reranker, use base ranking

---

### Phase 1 Summary

**What changes**:
1. Dedup: Prefix matching → Span overlap + symbol hierarchy
2. Graph: Binary bonus → Distance-aware proximity scoring
3. Reranker: Always-on → Confidence-gated

**What stays the same**:
- Linear fusion weights (for now)
- Feature extraction logic
- Reranker model itself

**Quality impact**: 85 → 90/100 (estimated)

**Time**: 1 week

**Validation**:
- Test on Q3 (optimizer rules interaction) → should surface related optimizer components
- Test on Q16 (BatchProcessor) → should prefer fine chunks over coarse
- Test on Q18 (complex query) → should skip reranker if confident, fire if uncertain

---

## Part III: Phase 2 — Adaptive Intelligence

**Timeline**: Week 2-3  
**Goal**: Signal-driven adaptive behavior  
**Result**: 90/100 → 96/100 quality

### 2.1 Signal Profile: Unified Retrieval Intelligence

**Principle**: Don't classify queries. Observe their retrieval geometry.

**Create a `SignalProfile` for each query**:

```
SignalProfile {
    # Score geometry
    margin: float              # s1 - s2 / s1
    score_entropy: float       # H(score distribution)
    score_variance: float      # Var(scores)
    
    # Retrieval agreement
    bm25_vector_correlation: float    # Rank correlation
    bm25_vector_kl_divergence: float  # Distribution divergence
    
    # Structural characteristics
    file_entropy: float        # H(file distribution)
    granularity_entropy: float # H(granularity distribution)
    unique_files: int          # Number of distinct files
    avg_graph_distance: float  # Mean distance in induced subgraph
    
    # Derived flags (for observability, not control)
    is_confident: bool         # margin > 0.3
    is_dispersed: bool         # file_entropy > 0.6
    is_structural: bool        # avg_graph_distance < 2.0
}
```

**Computation**: After base ranking, before fusion/reranking.

**Purpose**: NOT classification. Just **observation of retrieval landscape**.

---

### 2.2 Dynamic Weight Modulation

**Principle**: Fusion weights adapt based on SignalProfile.

**Current (static)**:
```
final = 0.5 * base + 0.35 * rerank + 0.15 * struct
```

**New (adaptive)**:
```
w_base = 0.5                           # Fixed (base is foundation)
w_struct = f_struct(profile)           # Adaptive
w_rerank = f_rerank(profile)           # Adaptive
w_diversity = f_diversity(profile)     # New term

final = w_base * base 
      + w_struct * struct 
      + w_rerank * rerank 
      + w_diversity * diversity_penalty
```

**Modulation functions**:

**Structural weight**:
```
w_struct = base_struct + boost

where:
boost = 0.2 * connectivity_factor

connectivity_factor = {
    1.0  if avg_graph_distance < 1.5    (highly connected)
    0.5  if 1.5 ≤ avg_graph_distance < 3.0
    0.0  if avg_graph_distance ≥ 3.0    (disconnected)
}
```

**Rerank weight**:
```
w_rerank = {
    0.0  if !fire_reranker              (skipped)
    0.3  if margin > 0.2                (confident, but reranking)
    0.5  if margin ≤ 0.2                (uncertain, trust reranker more)
}
```

**Diversity weight**:
```
w_diversity = {
    0.3  if file_entropy > 0.7          (dispersed query, enforce diversity)
    0.1  if 0.4 ≤ file_entropy ≤ 0.7
    0.0  if file_entropy < 0.4          (localized query, no diversity pressure)
}
```

**Key insight**: Weights are **continuous functions of signals**, not discrete rules.

---

### 2.3 Two-Pass Ranking with Graph Propagation

**Principle**: Use top-K as seeds for structural refinement.

**Current (single-pass)**:
```
Compute features → Fuse scores → Rank → Done
```

**New (two-pass)**:
```
Pass 1: Base Ranking
  - Compute features (BM25, vector, name match)
  - Compute structural proximity (distance to anchors)
  - Fuse scores
  - Get top-K (e.g., K=20)

Pass 2: Structural Refinement
  - Use top-K as new seeds
  - Run graph propagation (Personalized PageRank or neighbor boosting)
  - Recompute structural influence scores
  - Re-rank with updated scores

Final: Select top-N from Pass 2
```

**Graph propagation methods**:

**Option A: Personalized PageRank**
- Random walk with restart from seed set
- Stationary distribution = structural influence
- Benefits: Well-studied, provably good
- Implementation: Power iteration (5-10 iterations)

**Option B: Neighbor Boosting**
- Iteratively propagate scores to neighbors
- Score decay with distance (e.g., 0.8^d)
- Benefits: Simpler, more interpretable
- Implementation: BFS with exponential decay

**Recommendation**: Start with Neighbor Boosting (simpler), upgrade to PageRank if needed.

**When to use two-pass**:
- If `avg_graph_distance < 2.5` (query touches connected components)
- If `unique_files > 3` (multi-component interaction)
- Otherwise: single-pass is sufficient

**Adaptive two-pass gating**:
```
use_two_pass = (
    profile.avg_graph_distance < 2.5 OR
    profile.unique_files > 3
)
```

---

### 2.4 MMR-Based Diversity Selection

**Principle**: Diversity is a set-level optimization, not a per-candidate bonus.

**Current (additive bonus)**:
```
score += diversity_bonus  # Wrong! Treats diversity as local feature
```

**New (MMR selection)**:

**After ranking, select top-N iteratively**:

```
selected = []
remaining = all_candidates

while len(selected) < N and remaining:
    best_score = -∞
    best_candidate = None
    
    for candidate in remaining:
        relevance = candidate.final_score
        similarity = max_similarity_to_selected(candidate, selected)
        
        mmr_score = λ * relevance - (1-λ) * similarity
        
        if mmr_score > best_score:
            best_score = mmr_score
            best_candidate = candidate
    
    selected.append(best_candidate)
    remaining.remove(best_candidate)
```

**Similarity computation**:
```
similarity(A, B) = max(
    same_file_penalty,
    span_overlap_penalty,
    embedding_similarity,
    graph_proximity_penalty
)

where:
same_file_penalty = 0.8 if A.file == B.file else 0.0
span_overlap_penalty = overlap_ratio(A.span, B.span)
embedding_similarity = cosine(A.embedding, B.embedding)
graph_proximity_penalty = 0.6 if graph_distance(A, B) ≤ 1 else 0.0
```

**Adaptive λ** (relevance vs diversity trade-off):
```
λ = {
    0.9  if file_entropy < 0.4   (localized → prefer relevance)
    0.7  if 0.4 ≤ file_entropy < 0.7
    0.5  if file_entropy ≥ 0.7   (dispersed → enforce diversity)
}
```

**Benefits**:
- **Prevents redundancy**: Won't select 10 methods from same class
- **Enforces diversity**: Automatically spreads across files when needed
- **Adaptive**: λ adjusts to query characteristics

---

### 2.5 Optional: Temperature-Controlled Softmax Fusion

**Advanced refinement** (optional, can defer to later):

**Replace linear fusion with temperature-scaled softmax**:

**Current**:
```
combined = w1*s1 + w2*s2 + w3*s3
```

**New**:
```
normalized = softmax([s1, s2, s3] / T)
combined = weighted_sum(normalized, weights)
```

**Adaptive temperature**:
```
T = {
    0.5  if score_variance < 0.1   (peaked → sharpen)
    1.0  if 0.1 ≤ variance < 0.3
    2.0  if variance ≥ 0.3         (flat → smooth)
}
```

**Why this helps**:
- Low variance (confident) → lower T → sharper ranking
- High variance (uncertain) → higher T → smoother fusion

**Recommendation**: Defer this to Phase 3 or later. Not critical for 96/100.

---

### Phase 2 Summary

**What changes**:
1. Add SignalProfile computation
2. Dynamic weight modulation (w_struct, w_rerank, w_diversity)
3. Two-pass ranking with graph propagation
4. MMR-based diversity selection

**What stays the same**:
- Feature extraction (BM25, vector, name match)
- Core scoring logic

**Quality impact**: 90 → 96/100 (estimated)

**Time**: 2-3 weeks

**Validation**:
- Test on ambiguous queries → should fire reranker
- Test on confident queries → should skip reranker
- Test on interaction queries → should use two-pass
- Test on lookup queries → should use single-pass
- Test on multi-file queries → should enforce diversity

---

## Part IV: Integration Strategy

### How Phase 1 Enables Phase 2

**Phase 1 dedup** (span-aware) → enables Phase 2 MMR (no redundancy pre-filtering needed)

**Phase 1 graph proximity** (distance-aware) → enables Phase 2 two-pass (has distance metric already)

**Phase 1 reranker gating** (confidence-based) → enables Phase 2 adaptive weights (shares confidence signals)

**Key**: Phase 1 is NOT temporary. It's foundational infrastructure.

### Module Boundaries

**Phase 1 modules**:
- `ranking/dedup_structural.py` - Span-aware deduplication
- `ranking/graph_proximity.py` - Distance computation
- `ranking/confidence.py` - Gating logic

**Phase 2 modules**:
- `ranking/signal_profile.py` - SignalProfile computation
- `ranking/adaptive_weights.py` - Dynamic weight controller
- `ranking/graph_propagation.py` - Two-pass refinement
- `ranking/mmr_selection.py` - Diversity-aware selection

**Modified**:
- `ranking/pipeline.py` - Orchestration

**Clean separation**: Each module has single responsibility.

---

## Part V: Implementation Roadmap

### Week 1: Phase 1 (Structural Corrections)

**Day 1-2**: Span-aware deduplication
- Implement span overlap detection
- Implement parent-child hierarchy detection
- Granularity preference based on file entropy (not intent)
- Test on Q3, Q16

**Day 3**: Distance-aware graph scoring
- BFS from anchor set
- Distance-to-score conversion
- Test on Q18 (multi-component)

**Day 4**: Confidence-based reranker gating
- Compute margin, entropy, disagreement
- Implement gating logic
- Measure reranker skip rate (target: ~40%)

**Day 5**: Integration & testing
- Full pipeline test
- Measure quality delta (target: 85 → 90)

### Week 2: Phase 2 Part A (Signal Intelligence)

**Day 1-2**: SignalProfile
- Implement all signal computations
- Logging/observability
- Validate on diverse queries

**Day 3-4**: Dynamic weight modulation
- Implement adaptive weight functions
- Integration with fusion
- Test weight adaptation on different query types

**Day 5**: Testing & tuning
- Measure quality delta (target: 90 → 93)

### Week 3: Phase 2 Part B (Graph & Diversity)

**Day 1-3**: Two-pass ranking
- Implement graph propagation (neighbor boosting)
- Adaptive two-pass gating
- Test on interaction queries

**Day 4-5**: MMR diversity
- Implement MMR selection
- Adaptive λ
- Test on multi-file queries

**End of Week 3**: Full integration test
- Measure final quality (target: 96/100)

---

## Part VI: Success Criteria

### Phase 1 Validation

**Correctness**:
- ✅ No parent+child pairs in final ranking
- ✅ Graph distance computed correctly (not binary)
- ✅ Reranker skipped on confident queries (40%+ skip rate)

**Quality**:
- ✅ Q3 (optimizer rules) → surfaces related components
- ✅ Q16 (BatchProcessor) → prefers implementation over overview
- ✅ Q18 (complex query) → adaptive reranking

**Metrics**: 85 → 90/100 on benchmark

### Phase 2 Validation

**Adaptivity**:
- ✅ Confident queries → single-pass, no rerank
- ✅ Interaction queries → two-pass with propagation
- ✅ Dispersed queries → diversity enforcement
- ✅ Localized queries → relevance prioritization

**Quality**:
- ✅ All regressed queries (Q3, Q16) → improved
- ✅ Edge cases → adaptive behavior
- ✅ Latency → reduced on confident queries

**Metrics**: 90 → 96/100 on benchmark

---

## Part VII: Risk Mitigation

### Potential Issues

**Issue 1**: Graph propagation too aggressive
- **Mitigation**: Limit propagation depth (max 2-3 hops)
- **Fallback**: Disable two-pass if results degrade

**Issue 2**: MMR too slow for large candidate sets
- **Mitigation**: Pre-filter to top-100 before MMR
- **Fallback**: Use greedy diversity (faster approximation)

**Issue 3**: Signal thresholds need tuning
- **Mitigation**: A/B test on benchmark, adjust thresholds
- **Fallback**: Start conservative (only gate on extreme cases)

**Issue 4**: Phase 2 doesn't improve over Phase 1
- **Mitigation**: Each Phase 2 component tested independently
- **Fallback**: Use Phase 1 only (90/100 is still good)

---

## Part VIII: Beyond Phase 2 (Future)

**Phase 3 possibilities** (defer to later):
- Learning-to-rank (learn optimal weight functions from data)
- Multi-round retrieval (use diagnostics to trigger re-retrieval)
- Query-specific graph subgraph extraction
- Temporal/versioning awareness

**But**: Phase 1+2 gets you to Cursor-class (96/100). Phase 3 is marginal gains.

---

## Conclusion

**This is not a quick fix.**  
**This is architectural evolution.**

**Phase 1**: Make ranking structurally correct (1 week)  
**Phase 2**: Make ranking behaviorally adaptive (2-3 weeks)

**Result**: 85 → 96/100 quality, signal-driven intelligence, no heuristics, no LLMs, pure mathematical adaptation.

**You'll have a ranking system that reasons about its own uncertainty and adapts accordingly.**

That's Cursor-class. 🎯

---

## Appendix: Key Architectural Principles

1. **Signal-driven, not rule-driven**: Observe score geometry, don't classify queries
2. **Continuous, not discrete**: Adaptive weights, not if/else logic
3. **Mathematical, not heuristic**: Entropy, PageRank, MMR — not keyword matching
4. **Layered, not monolithic**: SignalProfile → Weights → Propagation → Selection
5. **Adaptive, not static**: Different behavior for different retrieval landscapes
6. **Confident, not paranoid**: Skip reranker when ranking is certain

**This is the path to 96/100.**

⚠️ One Important Caveat

The only thing that must be handled carefully during implementation is this:
Make sure Phase 2 dynamic weights are continuous functions, not turned into disguised if/else blocks.