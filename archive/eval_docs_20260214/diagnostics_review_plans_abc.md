# Post-Implementation Diagnostics Review — Plans A, B, C

## Executive Summary

**Root Cause Identified:** Intelligence Layer L1/L2/L3 is **over-pruning context** (80%+ reduction) without compensating recovery. Plan C mechanical fixer was **never triggered** because ABRM is disabled on cold_start (all runs are cold_start).

| Run | Date | Queries | Key Issue |
|-----|------|---------|-----------|
| Baseline | Jan 31 | 1,3,5,8,16,18 | Pre-Plans A/B/C |
| Latest | Feb 3 18:55 | 1,3,5,8,16,18 | Post-Plans A/B/C |

---

## Overall Score Trends

### Context Token Utilization (Latest Run)

| Query | Before Intelligence | After Intelligence | Reduction | P1 Verdict |
|-------|---------------------|-------------------|-----------|------------|
| Q1 | 3200 | 565 | **82%** | SUFFICIENT |
| Q3 | 3200 | ? | ? | SUFFICIENT |
| Q5 | 3200 | ? | ? | SUFFICIENT |
| Q8 | 3200 | ? | ? | ? |
| Q16 | 3200 | 863 | **73%** | SUFFICIENT (false positive) |
| Q18 | 3200 | ? | ? | ? |

**Mechanical Fixer:** NOT TRIGGERED (0 actions across all queries)
**ABRM:** NOT ACTIVATED (disabled on cold_start)

---

## Per-Query Breakdown

### Query 1: Admin Search Endpoint Trace

| Metric | Baseline (Jan 31) | Latest (Feb 3) |
|--------|-------------------|----------------|
| tokens_out | 2264 | 3000 |
| Completeness | High (enumerated components) | High (improved) |

**Diagnostics:**
- P1: `SUFFICIENT` (semantic=0.73)
- P3: `UNSTABLE_CONTEXT` (cold_start=true)
- P4: `SHALLOW_OK`

**Intelligence Impact:** 3200 → 565 tokens (82% pruned)

**Why Fixer Didn't Trigger:**
- `abrm_disable_on_cold_start: true` in config
- P3 indicates cold_start, so ABRM skipped

**Result:** ✅ Query 1 appears OK despite aggressive pruning

---

### Query 3: Query Optimizer Conflicts

| Metric | Baseline (Jan 31) | Latest (Feb 3) |
|--------|-------------------|----------------|
| tokens_out | 1423 | 664 |
| Completeness | Detailed (5 rules explained) | Shorter but accurate |

**Diagnostics:**
- P1: `SUFFICIENT`
- P3: `UNSTABLE_CONTEXT` (cold_start)

**Why Shorter:** Intelligence pruned context, model gave more concise answer.

**Result:** ⚠️ Shorter response, may lose depth

---

### Query 5: Cache Miss + Promotion

| Metric | Baseline (Jan 31) | Latest (Feb 3) |
|--------|-------------------|----------------|
| tokens_out | 2105 | 1680 |
| Completeness | Full L1/L2/L3 explanation | Full explanation |

**Result:** ✅ Comparable quality

---

### Query 8: ConnectionPool Timeout

| Metric | Baseline (Jan 31) | Latest (Feb 3) |
|--------|-------------------|----------------|
| tokens_out | 816 | 1167 |
| Completeness | Explains acquire/timeout | Also explains (improved) |

**Result:** ✅ Improved output

---

### Query 16: BatchProcessor Partial Failures

| Metric | Baseline (Jan 31) | Latest (Feb 3) |
|--------|-------------------|----------------|
| tokens_out | 412 | **108** |
| Answer | "BatchProcessor not in context" | "BatchProcessor not in context" |

**Diagnostics:**
- P1: `SUFFICIENT` ← **FALSE POSITIVE**
- P4: `DETAILED_REQUIRED`
- Intelligence: 3200 → 863 tokens (73% pruned)

**Root Cause:**
1. **Retrieval failure:** BM25 returned only 28 candidates (vs 50 for other queries)
2. **P1 false positive:** Semantic score 0.73 incorrectly marked SUFFICIENT
3. **No recovery:** Mechanical fixer disabled due to cold_start

**Result:** ❌ **CRITICAL REGRESSION** - Complete answer failure

---

### Query 18: Optimizer Rules + Plan Caching

| Metric | Baseline (Jan 31) | Latest (Feb 3) |
|--------|-------------------|----------------|
| tokens_out | 3274 | 3057 |
| Completeness | Detailed | Detailed |

**Result:** ✅ Comparable quality

---

## Systemic Findings

### What Improved

1. **Query 1:** More comprehensive answer (2264 → 3000 tokens)
2. **Query 8:** Better explanation of timeout behavior
3. **MMR diversity:** 84 similar candidates de-prioritized (Plan B working)

### What Regressed

1. **Query 16: Complete failure** - BatchProcessor not retrieved
2. **Query 3: Shorter answer** - May lack depth

### Root Causes

#### 1. Intelligence Over-Pruning (Critical)

```
Context tokens before: 3200
Context tokens after:  565-863 (73-82% reduction)
```

Intelligence L1/L2/L3 is removing too much context. Without Plan C recovery (mechanical fixer), this causes information loss.

#### 2. ABRM Never Activates (Critical)

```yaml
# From config:
abrm_disable_on_cold_start: true
```

All runs report `cold_start: true` in P3 diagnostics. This means:
- ABRM template is NEVER selected
- No explicit "Assumptions" section in outputs
- No mechanical fixer recovery

#### 3. P1 False Positives (High)

Query 16 P1 = `SUFFICIENT` with semantic=0.73, but answer was "not in context."

The semantic similarity score doesn't detect **topic mismatch** - retrieved code was about caching/indexing, not batch processing.

#### 4. Retrieval Misfires (Medium)

Query 16 BM25 returned only 28 candidates (vs 50 for other queries). This suggests:
- "BatchProcessor" keyword not in indexed corpus
- Or indexed files don't contain relevant code

---

## Configuration Analysis

```yaml
# Plan C config (ACTIVE but NOT TRIGGERED)
mechanical_fixer_enabled: true
abrm_enabled: true
abrm_disable_on_cold_start: true  # ← BLOCKS ALL ACTIVATION
```

**Problem:** Since ALL runs are cold_start, ABRM is never used.

---

## Recommendations

### Immediate Fixes (High Confidence)

| Fix | Confidence | Impact |
|-----|------------|--------|
| **Disable `abrm_disable_on_cold_start`** | HIGH | Enables ABRM template on all runs |
| **Lower P1 semantic threshold** | HIGH | Reduce false positives (0.73 → 0.80) |
| **Add "batch" to retrieval synonyms** | MEDIUM | Help Query 16 retrieval |

### Config Change

```yaml
intelligence:
  abrm_disable_on_cold_start: false  # Enable ABRM even on cold start
```

### P1 Threshold Adjustment

```yaml
signals:
  semantic:
    sufficient_threshold: 0.80  # Raise from ~0.73
```

---

## Conclusion

**Plans A and B are working** (MMR diversity, granularity boost, graph stitch all active).

**Plan C (Mechanical Fixer + ABRM) is configured but NEVER TRIGGERS** because:
1. `abrm_disable_on_cold_start: true` blocks activation
2. All queries report `cold_start: true` in P3

**The single highest-leverage fix:** Disable `abrm_disable_on_cold_start` in config to allow recovery mechanisms to engage.
