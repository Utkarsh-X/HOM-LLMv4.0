# Intelligence Diagnostics: L1, L2, L3 Signal Reference

> **Read-only observability into the context assembly pipeline**

This document explains the **three-layer diagnostic system** in the HOM-LLM Intelligence module. These diagnostics are **read-only, deterministic, and non-mutating** — they explain system behavior without altering it.

---

## 📊 Overview

| Level | Name | Focus | Key Question |
|-------|------|-------|--------------|
| **L1** | Structural Diagnostics | Per-block analysis | *What's inside each block?* |
| **L2** | Semantic Diagnostics | Block relationships | *How do blocks relate to each other?* |
| **L3** | Cognitive Diagnostics | Query alignment | *Does the context serve the query?* |

---

## Level 1: Structural Diagnostics (Per-Block Analysis)

**Purpose:** Analyze the internal composition of each context block to understand signal vs. noise.

### Signals Captured

#### 🔢 Token Breakdown
Classifies tokens into categories to understand block composition:

| Signal | Description |
|--------|-------------|
| `code_logic_pct` | Percentage of actual implementation logic |
| `comments_pct` | Percentage of comments |
| `docstrings_pct` | Percentage of docstrings |
| `error_handling_pct` | Percentage of error handling (`try/except`) |
| `logging_pct` | Percentage of logging statements |
| `imports_boiler_pct` | Percentage of imports and boilerplate |
| `control_flow_pct` | Percentage of control flow (`if/for/while`) |
| `signatures_pct` | Percentage of function/class signatures |

#### 🏷️ Identifier Density
Analyzes identifier usage patterns:

| Signal | Description |
|--------|-------------|
| `total_unique` | Count of unique identifiers in the block |
| `top_repeated` | Most frequently repeated identifiers with counts |
| `density_ratio` | Ratio of identifiers to total tokens |

#### 🏗️ Structural Payload
Counts structural elements:

| Signal | Description |
|--------|-------------|
| `function_count` | Number of function definitions |
| `class_count` | Number of class definitions |
| `method_count` | Number of method definitions |
| `decorator_count` | Number of decorators |
| `nested_depth_max` | Maximum nesting depth |

#### 🔄 Redundancy Hints
Detects potential noise:

| Signal | Description |
|--------|-------------|
| `repeated_patterns` | Detected repeated code patterns |
| `error_handling_blocks` | Count of error handling blocks |
| `logging_calls` | Count of logging calls |
| `has_repeated_logging` | Flag for excessive logging |
| `has_repeated_error_handling` | Flag for repeated try/except |
| `boilerplate_score` | 0.0–1.0 score for boilerplate content |

#### 📈 Aggregate Metrics
Block-level summary metrics:

| Signal | Description |
|--------|-------------|
| `signal_ratio` | Proportion of useful code content (0.0–1.0) |
| `noise_ratio` | Proportion of low-value content (0.0–1.0) |
| `warnings` | List of generated warnings for the block |

---

## Level 2: Semantic Diagnostics (Relational Analysis)

**Purpose:** Analyze relationships *between* blocks to detect redundancy, gaps, and flow issues.

### Signals Captured

#### 🕸️ Similarity Graph
Pairwise similarity between blocks:

| Signal | Description |
|--------|-------------|
| `block_a_id`, `block_b_id` | IDs of compared blocks |
| `score` | Combined similarity score (0.0–1.0) |
| `signals.identifier_overlap` | Ratio of shared identifiers (40% weight) |
| `signals.file_proximity` | Same file/directory indicator (30% weight) |
| `signals.structural_similarity` | Similar structure score (30% weight) |

#### 🔗 Redundancy Clusters
Groups of overlapping blocks:

| Signal | Description |
|--------|-------------|
| `cluster_id` | Unique cluster identifier |
| `block_ids` | List of blocks in the cluster |
| `total_tokens` | Combined token count |
| `dominant_block_id` | Block with highest signal ratio |
| `dominant_signal_ratio` | Signal ratio of the dominant block |
| `token_pct` | Percentage of total context tokens |

#### 🗺️ Concept Coverage Map
How concepts are distributed across blocks:

| Signal | Description |
|--------|-------------|
| `concept` | The concept name/identifier |
| `block_ids` | Blocks covering this concept |
| `token_weight` | Total tokens allocated to this concept |
| `coverage_pct` | Percentage of context covering this concept |

#### 🔀 Dependency Analysis
Structural dependencies between blocks:

| Signal | Description |
|--------|-------------|
| `max_depth` | Maximum dependency chain depth |
| `root_blocks` | Blocks with no dependencies |
| `leaf_blocks` | Blocks that nothing depends on |
| `orphan_blocks` | Blocks with no connections |
| `edges` | List of `(from_block, to_block)` dependencies |

#### 📖 Narrative Flow
Ordering and coherence analysis:

| Signal | Description |
|--------|-------------|
| `score` | Quality rating (`"good"`, `"fair"`, `"poor"`) |
| `explanation` | Human-readable explanation |
| `violations` | List of detected flow problems |

---

## Level 3: Cognitive Diagnostics (Query Alignment)

**Purpose:** Determine if the context adequately serves the query's intent with minimal cognitive burden.

### Signals Captured

#### 🎯 Query Intent Decomposition
Parses the query into semantic obligations:

| Signal | Description |
|--------|-------------|
| `intent_type` | Primary intent (`WHAT`, `HOW`, `WHY`, `COMPARE`, `TRACE`, `RESOLVE`) |
| `secondary_type` | Secondary intent if applicable |
| `concepts` | Required concepts extracted from query |
| `actions` | Action verbs (`EXPLAIN`, `RESOLVE`, `COMPARE`, `TRACE`, etc.) |
| `is_explanatory` | Does the query require explanation? |
| `is_comparative` | Does the query require comparison? |
| `is_procedural` | Does the query require step-by-step? |

#### 🏷️ Explanatory Role Classification
Assigns semantic roles to each block:

| Role | Description |
|------|-------------|
| `DEFINE` | Introduces/defines a concept (class/function definitions) |
| `IMPLEMENT` | Contains implementation logic |
| `USE` | Uses/calls other components |
| `EXPLAIN` | Contains explanatory content (docstrings, comments) |
| `SUPPORT` | Supporting/utility code |
| `NOISE` | Low-signal content (logging, boilerplate) |

Each block receives:
- `primary_role` — The dominant role
- `secondary_role` — Secondary role if close in score
- `confidence` — Classification confidence (0.0–1.0)
- `role_scores` — Scores for all role categories
- `reasons` — Human-readable classification reasons

#### 🧩 Concept Coverage & Gap Detection
Cross-references query concepts with block coverage:

| Signal | Description |
|--------|-------------|
| `defined` | Is the concept defined in context? |
| `implemented` | Is the concept implemented in context? |
| `explained` | Is the concept explained in context? |
| `define_blocks` | Blocks that define this concept |
| `implement_blocks` | Blocks that implement this concept |
| `explain_blocks` | Blocks that explain this concept |
| `coverage_score` | Overall coverage score for this concept |

Aggregate metrics:
- `fully_covered` — Concepts with all three (define, implement, explain)
- `partially_covered` — Concepts with 1-2 of three
- `uncovered` — Concepts with none

#### 🧠 Cognitive Load Estimation
Estimates mental effort required per block:

| Signal | Description |
|--------|-------------|
| `load_level` | `LOW`, `MEDIUM`, or `HIGH` |
| `load_score` | Numeric load score (0.0–1.0) |
| `nesting_score` | Contribution from nesting depth |
| `branching_score` | Contribution from branching/control flow |
| `identifier_churn` | Contribution from identifier complexity |
| `implicit_deps_score` | Contribution from implicit dependencies |
| `role_mismatch_score` | Penalty for role vs. content mismatch |

Aggregate metrics:
- `high_load_count` — Blocks requiring high cognitive effort
- `average_load_score` — Mean cognitive load across context
- `overall_load` — Summary classification (`LOW`/`MEDIUM`/`HIGH`)

#### ⚖️ Explanatory Balance
Role distribution analysis:

| Signal | Description |
|--------|-------------|
| `define_count` | Number of DEFINE blocks |
| `implement_count` | Number of IMPLEMENT blocks |
| `explain_count` | Number of EXPLAIN blocks |
| `use_count` | Number of USE blocks |
| `support_count` | Number of SUPPORT blocks |
| `noise_count` | Number of NOISE blocks |
| `is_balanced` | Are roles well-distributed? |

#### ❌ Failure Mode Classification
Identifies the dominant problem if any:

| Failure Mode | Description |
|--------------|-------------|
| `NONE` | No significant issues detected |
| `MISSING_DEFINITION` | Key concepts lack definitions |
| `MISSING_EXPLANATION` | Implementation without explanation |
| `IMPLEMENTATION_ONLY` | Code without conceptual context |
| `HIGH_COGNITIVE_LOAD` | Context too complex to process |
| `LOW_COVERAGE` | Insufficient concept coverage |
| `ROLE_IMBALANCE` | Unbalanced explanatory roles |

---

## Diagnostic Output Structure

```
DiagnosticSnapshot
├── level1: StructuralDiagnostics
│   ├── status: "available" | "unavailable"
│   ├── reason: "" | error message
│   ├── blocks: tuple[IntraBlockDiagnostic, ...]
│   └── result: ContextDiagnosticResult
│
├── level2: SemanticDiagnostics
│   ├── status: "available" | "unavailable"
│   ├── reason: "" | error message
│   └── result: RelationalDiagnosticResult
│       ├── similarity_edges
│       ├── redundancy_clusters
│       ├── concept_coverage
│       ├── dependency_analysis
│       └── narrative_flow
│
└── level3: CognitiveDiagnostics
    ├── status: "available" | "unavailable"
    ├── reason: "" | error message
    └── result: Level3DiagnosticResult
        ├── intent
        ├── block_roles
        ├── concept_gaps
        ├── cognitive_load
        ├── explanatory_balance
        ├── primary_failure_mode
        └── warnings
```

---

## Design Constraints

All diagnostic layers adhere to strict constraints:

| Constraint | Description |
|------------|-------------|
| **Read-only** | Never modifies context, prompts, or state |
| **Deterministic** | Same input → Same output (no randomness) |
| **No LLM** | Uses only heuristic/rule-based analysis |
| **No ML** | No machine learning models or embeddings |
| **Query-scoped** | Operates on one context artifact at a time |
| **Explicit failures** | Unavailable diagnostics are represented, not hidden |

---

## Usage Example

```python
from homllm.intelligence.diagnostics_runner import run_diagnostics

# Run diagnostics on a context artifact
snapshot = run_diagnostics(context_artifact)

if snapshot:
    # Access L1 (per-block analysis)
    for block in snapshot.level1.blocks:
        print(f"Block {block.block_id}: signal={block.signal_ratio:.0%}")
    
    # Access L2 (redundancy clusters)
    if snapshot.level2.result:
        for cluster in snapshot.level2.result.redundancy_clusters:
            print(f"Cluster: {cluster.block_ids} ({cluster.token_pct:.0%} of tokens)")
    
    # Access L3 (failure mode)
    if snapshot.level3.result:
        print(f"Failure mode: {snapshot.level3.result.primary_failure_mode.value}")
```

---

## File Locations

| Component | Path |
|-----------|------|
| Diagnostic Runner | `src/homllm/intelligence/diagnostics_runner.py` |
| L1: Block Analysis | `src/homllm/intelligence/diagnostics/inspect_context.py` |
| L2: Relational Analysis | `src/homllm/intelligence/diagnostics/inspect_context_relations.py` |
| L3: Query Intent | `src/homllm/intelligence/diagnostics/context_level3/inspect_query_intent.py` |
| L3: Explanatory Roles | `src/homllm/intelligence/diagnostics/context_level3/inspect_explanatory_roles.py` |
| L3: Concept Gaps | `src/homllm/intelligence/diagnostics/context_level3/inspect_concept_gaps.py` |
| L3: Cognitive Load | `src/homllm/intelligence/diagnostics/context_level3/inspect_cognitive_load.py` |
| L3: Alignment Summary | `src/homllm/intelligence/diagnostics/context_level3/inspect_alignment_summary.py` |
| Interfaces | `src/homllm/intelligence/interfaces.py` |
| Diagnostic Controller | `src/homllm/intelligence/diagnostics/controller.py` |

---

*Last updated: February 2026*
