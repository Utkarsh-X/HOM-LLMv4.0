# Implementation Roadmap: 4-Week Plan

## Overview

This document provides a **day-by-day implementation plan** to upgrade your indexing system from 70/100 to 95/100 in 4 weeks.

**Prerequisites**:
- Python 3.10+
- ANTHROPIC_API_KEY environment variable
- 16GB RAM (for embedding model)
- ~50GB disk space (for indexes)

---

## Week 1: Foundation Upgrades

### Day 1-2: LLM Summarizer Implementation

**Goal**: Add LLM-powered file summarization

**Tasks**:
1. Create `llm_summarizer.py`
2. Test on 10-file sample repo
3. Measure token costs
4. Validate question quality

**Implementation**:
```bash
# 1. Install dependencies
pip install anthropic>=0.21.0

# 2. Create file
touch homllm/indexer/llm_summarizer.py

# 3. Copy code from 01_INDEXING_PHASE.md

# 4. Test
python -c "
from homllm.indexer.llm_summarizer import ClaudeHaikuSummarizer
summarizer = ClaudeHaikuSummarizer()
summary = summarizer.summarize_file(
    file_path='test.py',
    content='def hello(): pass',
    symbols=[],
    dependencies=[],
)
print(summary.questions)
"
```

**Success Criteria**:
- ✅ LLM generates 10 questions per file
- ✅ Questions are relevant to code content
- ✅ Cost is <$2 per 1000 files
- ✅ No crashes on malformed code

**Estimated Time**: 8 hours

---

### Day 3-4: Upgrade Hierarchical Chunker

**Goal**: Integrate LLM summarizer into chunking

**Tasks**:
1. Modify `_create_coarse_chunks()` in `hierarchical_chunker.py`
2. Add concept extraction logic
3. Test with/without LLM fallback
4. Validate chunk quality

**Implementation**:
```python
# Modify hierarchical_chunker.py __init__
def __init__(self, config, llm_summarizer=None):
    self.config = config
    self.llm_summarizer = llm_summarizer  # NEW

# Replace _create_coarse_chunks (see 01_INDEXING_PHASE.md for full code)
```

**Testing**:
```bash
# Test without LLM (fallback)
python -m homllm.indexer.test_chunker --no-llm

# Test with LLM
export ANTHROPIC_API_KEY="sk-ant-..."
python -m homllm.indexer.test_chunker --with-llm

# Compare outputs
diff coarse_chunk_no_llm.txt coarse_chunk_with_llm.txt
```

**Success Criteria**:
- ✅ Coarse chunks include LLM questions
- ✅ Graceful fallback if LLM unavailable
- ✅ No regression in indexing speed (<20% slower)

**Estimated Time**: 10 hours

---

### Day 5-6: Multi-Vector Indexer

**Goal**: Split LanceDB into 3 separate indexes

**Tasks**:
1. Create `multi_vector_indexer.py`
2. Modify pipeline to route chunks
3. Test index isolation
4. Verify search routing

**Implementation**:
```bash
# 1. Create file
touch homllm/indexer/multi_vector_indexer.py

# 2. Copy code from 01_INDEXING_PHASE.md

# 3. Test index creation
python -c "
from homllm.indexer.multi_vector_indexer import MultiVectorIndexer
from pathlib import Path
indexer = MultiVectorIndexer(Path('test_index'), embedder)
indexer.file_index.insert('file1', 'content', {})
indexer.symbol_index.insert('symbol1', 'content', {})
"

# 4. Verify 3 directories created
ls -lh test_index/
# Expected: files/, symbols/, relations/
```

**Success Criteria**:
- ✅ Three separate LanceDB tables created
- ✅ Chunks routed to correct index by granularity
- ✅ No cross-contamination between indexes
- ✅ Search latency per index <100ms

**Estimated Time**: 8 hours

---

### Day 7: Week 1 Integration Test

**Goal**: Full indexing pipeline with LLM + multi-vector

**Tasks**:
1. Index 100-file test repo
2. Measure indexing time
3. Measure token costs
4. Validate all 3 indexes populated

**Test Script**:
```python
# test_week1_integration.py
from pathlib import Path
from homllm.indexer.pipeline import IndexingPipeline
from homllm.common.config import IndexerConfig

# Configure with Week 1 upgrades
config = IndexerConfig(
    llm_enrichment_enabled=True,
    multi_vector_enabled=True,
    relationship_indexing_enabled=False,  # Week 2
)

# Index test repo
pipeline = IndexingPipeline(config)
pipeline.index_repository(Path("test_repos/sample_100_files"))

# Validate
assert (Path(".homllm/index/vectors/files").exists())
assert (Path(".homllm/index/vectors/symbols").exists())
print("Week 1 integration test passed!")
```

**Success Criteria**:
- ✅ 100 files indexed in <10 minutes
- ✅ LLM cost <$0.50
- ✅ All 3 indexes contain data
- ✅ Search returns results from file index

**Estimated Time**: 6 hours

---

## Week 2: Relationship Embeddings + Cross-Encoder

### Day 8-9: Relationship Embedder

**Goal**: Convert graph edges into searchable vectors

**Tasks**:
1. Create `relationship_embedder.py`
2. Extract call relationships from graph
3. Test relationship text generation
4. Index relationships

**Implementation**:
```python
# 1. Create relationship embedder
touch homllm/indexer/relationship_embedder.py

# 2. Test relationship text generation
from homllm.indexer.relationship_embedder import RelationshipEmbedder

embedder = RelationshipEmbedder()
text = embedder.create_call_relationship_text(
    caller=EntityInfo(name="process_payment", ...),
    callee=EntityInfo(name="validate_card", ...),
    call_context="Validates payment before processing",
)
print(text)
# Expected:
# "process_payment calls validate_card.
#  Caller: process_payment (payment.py:45)
#  ...
# "
```

**Success Criteria**:
- ✅ Relationship text is semantic (not just "A calls B")
- ✅ Includes context from both entities
- ✅ Embeddings are searchable

**Estimated Time**: 8 hours

---

### Day 10-11: Index Relationships

**Goal**: Populate relationship index from graph data

**Tasks**:
1. Modify pipeline to extract graph edges
2. Create relationship embeddings
3. Index in relation_index
4. Test graph search

**Implementation**:
```python
# Modify pipeline.py
def _index_relationships(self, entities: list[EntityInfo]):
    """Index entity relationships."""
    for entity in entities:
        # Extract call relationships
        if hasattr(entity, 'calls'):
            for callee_id in entity.calls:
                callee = self._get_entity_by_id(callee_id)
                if callee:
                    relation_text = self.relation_embedder.create_call_relationship_text(
                        caller=entity,
                        callee=callee,
                        call_context=f"Called from {entity.name}",
                    )
                    
                    self.multi_indexer.index_relationship(
                        relation_id=f"call:{entity.entity_id}:{callee_id}",
                        source_entity=entity.entity_id,
                        target_entity=callee_id,
                        relation_type="calls",
                        context=relation_text,
                    )
```

**Testing**:
```bash
# Search relationship index
python -m homllm.retrieval.test_relation_search \
  --query "What calls the payment processor?"

# Expected: Returns call relationships involving payment processing
```

**Success Criteria**:
- ✅ Call relationships indexed
- ✅ Import relationships indexed
- ✅ Inheritance relationships indexed
- ✅ Semantic search finds relationships

**Estimated Time**: 10 hours

---

### Day 12-13: Cross-Encoder Reranker

**Goal**: Add final precision boost to retrieval

**Tasks**:
1. Create `cross_encoder.py`
2. Download pretrained model
3. Test reranking latency
4. Integrate into pipeline

**Implementation**:
```bash
# 1. Install dependencies
pip install transformers>=4.30.0 torch>=2.0.0

# 2. Create file
touch homllm/retrieval/cross_encoder.py

# 3. Download model
python -c "
from transformers import AutoModel
AutoModel.from_pretrained('cross-encoder/ms-marco-MiniLM-L-6-v2')
"

# 4. Test reranking
python -m homllm.retrieval.test_cross_encoder
```

**Latency Test**:
```python
import time
from homllm.retrieval.cross_encoder import CrossEncoderReranker

reranker = CrossEncoderReranker()

# Test on 20 candidates
candidates = [...]  # Mock candidates
start = time.time()
reranked = reranker.rerank("test query", candidates, top_k=10)
latency = (time.time() - start) * 1000
print(f"Reranking latency: {latency:.1f}ms")

# Target: <150ms for 20 candidates
assert latency < 150
```

**Success Criteria**:
- ✅ Model loads successfully
- ✅ Reranking latency <150ms for 20 candidates
- ✅ Accuracy improves by 5-10% over RRF alone

**Estimated Time**: 8 hours

---

### Day 14: Week 2 Integration Test

**Goal**: Full pipeline with relationship index + cross-encoder

**Test Script**:
```python
# test_week2_integration.py
from homllm.retrieval.pipeline import EnhancedRetrievalPipeline

pipeline = EnhancedRetrievalPipeline(config, multi_indexer, bm25, embedder, log_dir)

# Test graph-aware search
results = pipeline.search("What calls the authentication function?")
assert len(results.candidates) > 0
assert any("calls" in c.provenance for c in results.candidates)

# Test cross-encoder reranking
assert "cross_encoder" in results.candidates[0].provenance

print("Week 2 integration test passed!")
```

**Success Criteria**:
- ✅ Graph search returns relationships
- ✅ Cross-encoder reranks top results
- ✅ End-to-end latency <500ms
- ✅ Accuracy improved vs Week 1

**Estimated Time**: 6 hours

---

## Week 3: Query Intelligence + Learning

### Day 15-16: LLM Query Preparation

**Goal**: Add intent classification and query expansion

**Tasks**:
1. Create enhanced `preparer.py`
2. Test intent classification accuracy
3. Test query expansion quality
4. Integrate with router

**Implementation**:
```bash
# 1. Create file
touch homllm/retrieval/preparer.py

# 2. Test intent classification
python -m homllm.retrieval.test_intent_classification

# Expected output:
# Query: "How does auth work?" → Intent: EXPLAIN ✓
# Query: "How to implement login?" → Intent: IMPLEMENT ✓
# Query: "Why is login failing?" → Intent: DEBUG ✓
# Accuracy: 90%
```

**Success Criteria**:
- ✅ Intent classification >85% accurate
- ✅ Query expansion adds relevant terms
- ✅ Latency <200ms per query
- ✅ Graceful fallback if LLM unavailable

**Estimated Time**: 10 hours

---

### Day 17-18: Query Router

**Goal**: Route queries to appropriate indexes based on intent

**Tasks**:
1. Create `query_router.py`
2. Implement intent-based routing logic
3. Test routing decisions
4. Measure latency improvement

**Implementation**:
```python
# Test routing logic
from homllm.retrieval.query_router import QueryRouter

router = QueryRouter(multi_indexer, bm25, config)

# EXPLAIN intent → file index
prepared = PreparedQuery(
    dense_query="How does the payment system work?",
    lexical_terms=["payment", "system"],
    intent=Intent.EXPLAIN,
)
routed = router.route(prepared)
assert "file_vector" in routed
assert "symbol_vector" not in routed

# IMPLEMENT intent → symbol index
prepared = PreparedQuery(
    dense_query="How to implement payment processing?",
    lexical_terms=["implement", "payment"],
    intent=Intent.IMPLEMENT,
)
routed = router.route(prepared)
assert "symbol_vector" in routed
assert "file_vector" not in routed
```

**Success Criteria**:
- ✅ EXPLAIN queries hit file index
- ✅ IMPLEMENT queries hit symbol index
- ✅ DEBUG queries hit multi-index + graph
- ✅ Routing adds no measurable latency

**Estimated Time**: 8 hours

---

### Day 19-20: Learning Loop

**Goal**: Log user interactions and train adaptive weights

**Tasks**:
1. Create `learning_loop.py`
2. Implement interaction logging
3. Test weight training
4. Set up weekly retraining job

**Implementation**:
```bash
# 1. Create file
touch homllm/retrieval/learning_loop.py

# 2. Test logging
python -c "
from homllm.retrieval.learning_loop import LearningLoop
loop = LearningLoop(Path('.homllm/learning'))
loop.log_interaction(
    query='test query',
    intent='IMPLEMENT',
    results=candidates,
    clicked_doc_id='file1:symbol1',
)
"

# 3. Simulate 100 interactions
python -m homllm.retrieval.simulate_interactions --count 100

# 4. Train weights
python -m homllm.retrieval.learning_loop --train

# 5. Check learned weights
cat .homllm/learning/learned_weights.json
```

**Success Criteria**:
- ✅ Interactions logged to JSONL file
- ✅ Weight training runs successfully
- ✅ Learned weights improve accuracy (test on holdout set)
- ✅ Weights deployable to production

**Estimated Time**: 10 hours

---

### Day 21: Week 3 Integration Test

**Goal**: Full "intelligent" retrieval pipeline

**Test Script**:
```python
# test_week3_integration.py
from homllm.retrieval.pipeline import EnhancedRetrievalPipeline

pipeline = EnhancedRetrievalPipeline(config, multi_indexer, bm25, embedder, log_dir)

# Test intent routing
results = pipeline.search("How does the auth system work?")
assert results.metadata["intent"] == "EXPLAIN"
assert "file_vector" in results.metadata["indexes_searched"]

# Test query expansion
results = pipeline.search("payment retry")
assert len(results.candidates) > 0
# Should find results even without exact "retry" keyword

# Test cross-encoder precision
assert results.candidates[0].hybrid_score > results.candidates[1].hybrid_score

print("Week 3 integration test passed!")
```

**Success Criteria**:
- ✅ Intent classification integrated
- ✅ Query routing works end-to-end
- ✅ Cross-encoder reranks correctly
- ✅ Learning loop logs interactions

**Estimated Time**: 6 hours

---

## Week 4: Production Hardening

### Day 22-23: Incremental Indexing

**Goal**: Only reindex changed files

**Tasks**:
1. Create `incremental_indexer.py`
2. Implement hash-based change detection
3. Test incremental update
4. Measure speed improvement

**Implementation**:
```python
# incremental_indexer.py
class IncrementalIndexer:
    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.hash_cache = self._load_hash_cache()
    
    def needs_reindex(self, file_path: Path) -> bool:
        """Check if file changed since last index."""
        current_hash = self._compute_hash(file_path)
        cached_hash = self.hash_cache.get(str(file_path))
        return current_hash != cached_hash
    
    def update_index(self, repo_path: Path):
        """Incrementally update index."""
        changed_files = []
        for file_path in repo_path.rglob("*.py"):
            if self.needs_reindex(file_path):
                changed_files.append(file_path)
        
        print(f"Reindexing {len(changed_files)} changed files")
        for file_path in changed_files:
            self._index_file(file_path)
            self.hash_cache[str(file_path)] = self._compute_hash(file_path)
        
        self._save_hash_cache()
```

**Testing**:
```bash
# Initial index
python -m homllm.indexer.pipeline --repo test_repo
# Time: 10 minutes

# Modify 5 files
touch test_repo/file{1..5}.py

# Incremental update
python -m homllm.indexer.incremental --repo test_repo
# Time: <1 minute (only 5 files reindexed)
```

**Success Criteria**:
- ✅ Only changed files reindexed
- ✅ Hash cache persisted to disk
- ✅ Incremental update <10% time of full reindex

**Estimated Time**: 8 hours

---

### Day 24-25: Batch LLM Optimization

**Goal**: Reduce LLM costs by batching

**Tasks**:
1. Modify `llm_summarizer.py` for batch processing
2. Test batch API calls
3. Measure cost savings
4. Optimize batch size

**Implementation**:
```python
# Modify llm_summarizer.py
def summarize_batch(self, files: list[dict]) -> dict[str, FileSummary]:
    """Batch summarize up to 10 files in one API call."""
    # See 01_INDEXING_PHASE.md for full code
    
    # Key optimization: 1 API call for 10 files
    # Cost savings: ~50% vs individual calls
```

**Testing**:
```bash
# Test batch summarization
python -m homllm.indexer.test_batch_llm --files 100

# Measure cost
# Individual: 100 files × $0.001 = $0.10
# Batch: 10 batches × $0.005 = $0.05
# Savings: 50%
```

**Success Criteria**:
- ✅ Batch size 10 files per API call
- ✅ Cost reduced by 40-50%
- ✅ Quality not degraded
- ✅ No timeout errors

**Estimated Time**: 6 hours

---

### Day 26-27: Async Retrieval

**Goal**: Parallelize BM25 + Vector searches

**Tasks**:
1. Convert retrieval to async
2. Test parallel execution
3. Measure latency improvement
4. Handle errors gracefully

**Implementation**:
```python
# async_retriever.py
import asyncio

class AsyncRetriever:
    async def search_parallel(self, query: str):
        """Execute BM25 and Vector searches in parallel."""
        bm25_task = asyncio.create_task(self.bm25.search_async(query))
        vector_task = asyncio.create_task(self.vector.search_async(query))
        
        # Wait for both
        bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)
        
        return bm25_results, vector_results
```

**Testing**:
```python
# Test latency
# Sequential: 50ms (BM25) + 100ms (Vector) = 150ms
# Parallel: max(50ms, 100ms) = 100ms
# Improvement: 33% faster
```

**Success Criteria**:
- ✅ BM25 and Vector searches run in parallel
- ✅ Latency reduced by 30-40%
- ✅ Error handling for failed searches
- ✅ No race conditions

**Estimated Time**: 8 hours

---

### Day 28: Final Integration & Deployment

**Goal**: End-to-end system ready for production

**Tasks**:
1. Full system test on 10k file repo
2. Performance benchmarking
3. Documentation
4. Deployment checklist

**Final Test**:
```bash
# 1. Index large repo
python -m homllm.indexer.pipeline --repo large_repo_10k_files

# Metrics:
# - Indexing time: <30 minutes
# - LLM cost: <$20
# - Index size: ~5GB
# - All 3 indexes populated

# 2. Search benchmark
python -m homllm.eval.benchmark_search --queries 100

# Metrics:
# - Avg latency: <500ms
# - P95 latency: <800ms
# - Precision@10: >90%
# - Recall@10: >85%

# 3. Learning loop
# - 100+ interactions logged
# - Weights trained successfully
# - Accuracy improved by 5%+
```

**Deployment Checklist**:
```bash
□ All tests passing
□ Documentation updated
□ API keys configured
□ Indexes backed up
□ Monitoring enabled
□ Learning loop scheduled (weekly cron)
□ Error alerting configured
□ Performance dashboard created
```

**Success Criteria**:
- ✅ System handles 10k file repo
- ✅ Search latency <500ms p95
- ✅ Precision >90%, Recall >85%
- ✅ Learning loop operational

**Estimated Time**: 8 hours

---

## Summary: Week-by-Week Progress

| Week | Deliverables | Impact | Score |
|------|-------------|---------|-------|
| Week 1 | LLM Summarizer + Multi-Vector Indexing | File-level semantic search | 70→85 |
| Week 2 | Relationship Embeddings + Cross-Encoder | Graph-aware search + precision | 85→92 |
| Week 3 | Query Intelligence + Learning Loop | Intent routing + adaptation | 92→95 |
| Week 4 | Production Hardening | Speed + reliability | 95→100 |

---

## Risk Management

### Risk 1: LLM Costs Too High

**Symptoms**: Indexing 10k files costs >$50

**Mitigation**:
1. Reduce batch size to 5 files per call
2. Use Haiku instead of Sonnet
3. Cache summaries aggressively
4. Fallback to template-based questions

**Fallback**: Disable LLM, use deterministic chunking only (70/100 system)

---

### Risk 2: Search Latency Too High

**Symptoms**: p95 latency >1 second

**Mitigation**:
1. Disable cross-encoder reranking
2. Reduce top_k to 10 instead of 20
3. Enable async retrieval
4. Cache frequent queries

**Fallback**: Use simple RRF fusion only (85/100 system)

---

### Risk 3: Index Size Too Large

**Symptoms**: Indexes exceed 20GB for 10k files

**Mitigation**:
1. Enable aggressive deduplication
2. Quantize embeddings to float16
3. Limit fine chunks to top 1000 per file
4. Use disk-based LanceDB tables

**Fallback**: Single index strategy (70/100 system)

---

## Next Steps

1. **Start Week 1** with LLM summarizer
2. **Track Progress** daily (use GitHub issues)
3. **Test Continuously** (don't wait until end)
4. **Measure Improvement** at each milestone

Continue to **`04_PERFORMANCE_OPTIMIZATIONS.md`** for advanced tuning.
