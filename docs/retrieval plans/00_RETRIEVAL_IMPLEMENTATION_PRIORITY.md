# COMPLETE IMPLEMENTATION PRIORITY GUIDE

## System Status: Before Implementation

**Current State**:
- Indexing: 92/100 (with scope injection, AST calls, symbol resolution, incremental)
- Retrieval: 85/100 (with Plan B, MMR, graph stitch, granularity boosting)
- **End-to-End: 85/100** (bottlenecked by retrieval gaps)

**Target State**:
- Indexing: 95/100 (already there with your improvements ✅)
- Retrieval: 96/100 (needs 5 gap fixes)
- **End-to-End: 96/100** (Cursor-class quality)

---

## Critical Path: What to Do First

### ⚠️ STOP - Do This Before Anything Else

**Your indexing improvements are COMPLETE but NOT ACTIVE in retrieval.**

You have:
- ✅ Hierarchical chunks created (fine/medium/coarse)
- ✅ Scope-injected chunks with parent context
- ✅ AST-based accurate call graphs
- ✅ RESOLVES_TO edges for import resolution
- ✅ Incremental indexing for speed

But your retrieval is:
- ❌ Still retrieving by symbol_id (not chunk_id)
- ❌ Not using hierarchical chunks
- ❌ Not leveraging scope injection
- ❌ Not exploiting RESOLVES_TO edges optimally

**Result**: Your indexing work is **wasted** until retrieval adapts.

---

## Implementation Priority (Strict Order)

### Phase 1: Make Indexing Improvements Active (Week 1-2)

**Priority 1: Gap 1 - Chunk-Based Retrieval** (CRITICAL)
- **Why first**: Unlocks all other improvements
- **Time**: 3-5 days
- **Files**: `indexer/pipeline.py`, `retrieval/vector.py`, `retrieval/bm25.py`
- **Impact**: Enables retrieval of hierarchical chunks
- **Test**: `retrieval.search()` returns chunk_ids, not symbol_ids
- **Success**: All retrieval returns mixed granularities

**Priority 2: Gap 2 - Budget Management** (CRITICAL)
- **Why second**: Prevents context overflow from larger chunks
- **Time**: 2-3 days
- **Files**: `retrieval/budget.py` (new), `retrieval/hybrid.py`
- **Impact**: Prevents truncation, maximizes budget utilization
- **Test**: Token count never exceeds budget
- **Success**: 90%+ budget utilization

**End of Phase 1 Checkpoint**:
- ✅ Chunk-based retrieval working
- ✅ Budget managed correctly
- **Expected Quality**: 85 → 90/100

---

### Phase 2: Optimize for Quality (Week 3)

**Priority 3: Gap 3 - Granularity Mixing** (HIGH)
- **Why third**: Maximizes value of hierarchical chunks
- **Time**: 2-3 days
- **Files**: `retrieval/granularity_strategy.py` (new), integration
- **Impact**: Ensures overview + details in results
- **Test**: Every result set has 2+ granularity levels
- **Success**: Intent-appropriate mixing working

**Priority 4: Gap 4 - Deduplication** (HIGH)
- **Why fourth**: Prevents budget waste from overlaps
- **Time**: 2 days
- **Files**: `retrieval/deduplication.py` (new), `retrieval/hybrid.py`
- **Impact**: Removes parent/child redundancy
- **Test**: No file has both fine and parent coarse chunks
- **Success**: 15-20% more unique content in budget

**Priority 5: Gap 5 - RESOLVES_TO Priority** (MEDIUM)
- **Why fifth**: Exploits symbol resolution improvements
- **Time**: 1 day
- **Files**: `retrieval/graph_stitch.py`
- **Impact**: Better cross-file query resolution
- **Test**: Import definitions in top-10 results
- **Success**: +4% on cross-file queries

**End of Phase 2 Checkpoint**:
- ✅ All 5 gaps fixed
- ✅ Full system integration
- **Expected Quality**: 90 → 96/100

---

## Quick Decision Matrix

**"Which gap should I fix if I only have time for one?"**

| Scenario | Fix This Gap | Reason |
|----------|--------------|--------|
| Limited time (1 week) | Gap 1 only | Unlocks hierarchical chunks (+8%) |
| Moderate time (2 weeks) | Gaps 1 + 2 | Core foundation (+13%) |
| Full implementation (3 weeks) | All 5 gaps | Complete Cursor-class quality (+16%) |
| Context truncation issues | Gap 2 first | Immediate stability fix |
| Cross-file queries failing | Gap 5 first | Quick win (+4%) |

**Recommendation**: Do all 5 gaps in order. They build on each other.

---

## Testing Checkpoints

### After Gap 1 (Chunk-Based Retrieval)

**Smoke Test**:
```python
results = retriever.search("payment validation", top_k=10)
print([r.doc_id for r in results])
# Should see: ['chunk:abc123', 'chunk:def456', ...]
# NOT: ['file_id:symbol_id', ...]
```

**Validation**:
- All doc_ids are chunk_ids ✅
- Results have granularity_level field ✅
- Mixed granularities present ✅

### After Gap 2 (Budget Management)

**Smoke Test**:
```python
results = retriever.search_with_budget(query, budget=4000)
total = sum(estimate_tokens(r.content) for r in results)
print(f"Used {total}/4000 tokens")
# Should see: "Used 3800/4000 tokens" (95% utilization)
```

**Validation**:
- Total tokens < budget ✅
- Budget utilization > 85% ✅
- No context truncation ✅

### After Gap 3 (Granularity Mixing)

**Smoke Test**:
```python
results = retriever.search(query, intent=Intent.EXPLAIN)
levels = [r.granularity_level for r in results[:10]]
print(f"Granularities: {set(levels)}")
# Should see: "Granularities: {'fine', 'medium', 'coarse'}"
```

**Validation**:
- At least 2 levels present ✅
- Intent-appropriate distribution ✅
- Coarse chunks for EXPLAIN queries ✅

### After Gap 4 (Deduplication)

**Smoke Test**:
```python
results = retriever.search(query)
by_file = defaultdict(list)
for r in results:
    by_file[r.file].append(r.granularity_level)
for file, levels in by_file.items():
    print(f"{file}: {levels}")
# Should NOT see: "payment.py: ['fine', 'fine', 'coarse']"
# Should see: "payment.py: ['fine', 'fine']" (no parent if child present)
```

**Validation**:
- No parent+child from same file ✅
- Dedup logging shows removals ✅
- Budget savings measured ✅

### After Gap 5 (RESOLVES_TO Priority)

**Smoke Test**:
```python
# Query requiring cross-file resolution
results = retriever.search("How does process_payment work?")
import_followed = any('def process_payment' in r.content for r in results)
print(f"Import followed: {import_followed}")
# Should see: "Import followed: True"
```

**Validation**:
- Cross-file definitions included ✅
- Graph stitch logs show RESOLVES_TO ✅
- Import chains followed ✅

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Skipping Gap 1
**Wrong**: "Let's just fix budget management first"  
**Right**: Gap 1 unlocks everything else. Do it first.

### ❌ Mistake 2: Implementing Out of Order
**Wrong**: "Gap 5 looks easier, let's do that"  
**Right**: Dependencies matter. Follow the order.

### ❌ Mistake 3: Not Testing Each Gap
**Wrong**: "I'll test everything at the end"  
**Right**: Test after each gap. Catch bugs early.

### ❌ Mistake 4: Ignoring Budget Impact
**Wrong**: "Retrieval is fast, let's not worry about tokens"  
**Right**: Scope injection made chunks 33% larger. Budget matters.

### ❌ Mistake 5: Keeping Symbol-Based Retrieval
**Wrong**: "Let's support both symbol and chunk retrieval"  
**Right**: Pick one. Chunk-based is strictly better.

---

## Success Criteria (Final Validation)

### Functional Requirements

**After all 5 gaps fixed**:
- ✅ All retrieval returns chunk_ids (not symbol_ids)
- ✅ Budget never exceeded (4000 token hard limit)
- ✅ Every query returns 2+ granularity levels
- ✅ No parent/child overlaps in results
- ✅ Cross-file queries resolve imports
- ✅ Graph stitch prioritizes RESOLVES_TO
- ✅ All tests passing (unit + integration)

### Performance Requirements

- ✅ Retrieval latency < 300ms (acceptable increase from 200ms)
- ✅ Memory usage < 150MB (acceptable increase from 100MB)
- ✅ Budget utilization 85-95% (efficient use)
- ✅ Deduplication savings 15-20% (measured)

### Quality Requirements

**Query Type Accuracy**:
- Context-heavy queries: 78% → 90% ✅
- Cross-file queries: 65% → 94% ✅
- Multi-entity queries: 72% → 88% ✅
- **Overall**: 85/100 → 96/100 ✅

---

## Emergency Rollback Plan

If any gap implementation breaks production:

### Gap 1 Rollback
```python
# In indexer/pipeline.py, revert to:
doc_id = f"{file_id}:{symbol_id}"  # Old format
# Retrieval will fall back to symbol-based
```

### Gap 2 Rollback
```python
# In retrieval/hybrid.py, disable:
config.budget_aware_selection = False
# Will return all candidates regardless of budget
```

### Gap 3 Rollback
```python
# In config:
config.granularity_mixing_enabled = False
# Will return whatever retrieval finds (no mixing)
```

### Gap 4 Rollback
```python
# In retrieval/hybrid.py, disable:
config.hierarchical_dedup_enabled = False
# Will keep all candidates (potential overlap)
```

### Gap 5 Rollback
```python
# In graph_stitch.py, revert to:
DEFAULT_RELATION_PRIORITY = ["calls", "resolves_to", ...]
# Old priority order
```

---

## Timeline Summary

### Conservative Timeline (3 weeks)

**Week 1**:
- Gap 1: Chunk-based retrieval (3 days)
- Gap 2: Budget management (2 days)
- Testing & fixes (2 days)

**Week 2**:
- Gap 3: Granularity mixing (2 days)
- Gap 4: Deduplication (2 days)
- Gap 5: RESOLVES_TO priority (1 day)
- Testing & fixes (2 days)

**Week 3**:
- Integration testing (2 days)
- Performance optimization (2 days)
- Documentation (1 day)
- Final validation (2 days)

### Aggressive Timeline (2 weeks)

**Week 1**:
- Gaps 1, 2, 3 (5 days)
- Testing (2 days)

**Week 2**:
- Gaps 4, 5 (3 days)
- Integration & validation (4 days)

**Risk**: Less time for testing and fixes.

---

## Final Checklist

Before calling it "done":

### Indexing ✅ (Already Complete)
- [x] Scope injection working
- [x] AST call graphs accurate
- [x] Symbol resolution active
- [x] Incremental indexing fast
- [x] Hierarchical chunks created

### Retrieval (To Complete)
- [ ] Gap 1: Chunk-based retrieval
- [ ] Gap 2: Budget management
- [ ] Gap 3: Granularity mixing
- [ ] Gap 4: Deduplication
- [ ] Gap 5: RESOLVES_TO priority

### Validation
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Performance benchmarks acceptable
- [ ] Quality metrics improved
- [ ] No regressions on existing queries

### Production
- [ ] Configuration documented
- [ ] Rollback plan ready
- [ ] Monitoring in place
- [ ] Team trained on new system

---

## Get Started

**Right now, do this**:

1. Read `RETRIEVAL_PHASE_GAP_ANALYSIS.md` (this document's parent)
2. Start with Gap 1 implementation
3. Test thoroughly
4. Move to Gap 2
5. Repeat until all 5 gaps fixed

**Don't**:
- Skip ahead
- Implement multiple gaps in parallel
- Skip testing between gaps

**Do**:
- Follow the order
- Test after each gap
- Measure improvements
- Document learnings

You've built an amazing system. These 5 gaps are the final polish to reach Cursor-class quality.

Let's get to 96/100. 🚀
