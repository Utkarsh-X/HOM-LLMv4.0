# STABILITY-FIRST CLEANING & OPTIMIZATION PLAN

## SECTION 1 - Objectives

This initiative is a stability-first structural cleanup of HOM-LLM(v2.0), not a redesign.

- Why we are cleaning:
  - Reduce drift sources caused by overlapping controls, shadow configs, and legacy artifacts.
  - Re-establish subsystem boundaries (retrieval, ranking, context, evaluation).
  - Restore trustworthy, repeatable comparisons across runs.
- What stability means operationally:
  - Same query suite + same config + same flags produces materially identical selection behavior.
  - No unexplained changes in selected blocks, token usage, or distinct file coverage.
  - Judge outputs are parse-clean, deduplicated, and reproducible.
- What counts as regression:
  - Selection changes without intentional scoped modification.
  - Token shrinkage/expansion beyond tolerance without explained cause.
  - Parse failures, duplicate query records, or missing query verdicts.
  - Judge aggregate movement outside tolerance after cleanup-only changes.
- What counts as architectural risk:
  - Responsibility overlap across layers.
  - Dormant branches and shadow pathways that can reactivate silently.
  - Multi-layer edits that make root-cause attribution impossible.

---

## SECTION 2 - Risk-Control Framework

Strict operating rules:

- No multi-component edits in a single phase.
- No behavior changes without telemetry comparison.
- Every modification must be reversible.
- Every phase ends with a stability verification run.

### Phase Safety Checklist

- [ ] Baseline snapshot captured (commit hash, command, config, run folder).
- [ ] Scope restricted to one subsystem and one intent.
- [ ] Fixed 6-query verification run completed.
- [ ] Judge output integrity verified (no parse errors, no duplicate query IDs).
- [ ] Telemetry diff reviewed against tolerances.
- [ ] Rollback command prepared and validated.
- [ ] Immediate rerun produces identical selected block IDs per query.

Gate rule: do not proceed to next phase unless all checklist items pass.

---

## SECTION 3 - Component Isolation Strategy

One subsystem per phase:

1. Retrieval Layer
2. Ranking Layer
3. Context Assembly Layer
4. Budget Allocation Logic
5. Evaluation/Judge Infrastructure
6. Telemetry Emission & Usage
7. Repository Structural Hygiene

For each phase, define and enforce:

- Why prioritized now.
- Artifacts to collect (code-path map, config map, telemetry fields, run outputs).
- Telemetry to compare (selection IDs, blocks, tokens, counts, latencies, judge scores).
- Invariants that must remain unchanged outside target subsystem.

---

## SECTION 4 - Deep Analysis Template (Reusable Per Phase)

### 1. Architectural Role Clarification

- What this subsystem must do.
- What this subsystem must not do.
- Upstream/downstream boundary conditions.

### 2. Dead Code & Dormant Logic Detection

- Unreachable branches.
- Zero-weight/no-op logic.
- Flags effectively always enabled/disabled.
- Duplicate/shadow config keys.

### 3. Objective Overlap Detection

- Is this subsystem enforcing behavior already enforced elsewhere?
- Is diversity/redundancy being applied twice?
- Is scoring duplicated across layers?

### 4. Stability Risk Surface Mapping

- Drift vectors.
- Variance vectors.
- Silent behavior-change vectors.

### 5. Safe Cleanup Proposal (per action)

- What is removed/changed.
- Why safe.
- Non-impact proof plan.
- Required telemetry checks.
- Rollback method.

---

## SECTION 5 - Controlled Execution Protocol

For each cleanup action:

1. Freeze state with commit snapshot.
2. Remove the smallest possible unit.
3. Run fixed 6-query verification suite.
4. Compare:
   - selected block IDs
   - blocks selected
   - context tokens used
   - distinct file count
   - retrieval count
   - retrieval/ranking timing
   - judge raw overall score
5. Rerun immediately with identical inputs.
6. If deviation exceeds tolerance, revert immediately.

### Numeric Tolerances

- Selected block IDs per query: exact match across immediate rerun.
- Blocks selected per query: delta = 0.
- Distinct files per query: delta = 0.
- Context tokens used per query: max of ±40 tokens or ±3%.
- Retrieval/ranking timings: ±15% (noise allowance only).
- Judge overall mean variance vs baseline: <= 0.2.
- Judge parse failures: 0 allowed.
- Duplicate judge records: 0 allowed.

---

## SECTION 6 - Evaluation Integrity Lock

- Use unique run directory per execution.
- Never append judge outputs onto reused files.
- Enforce exactly one record per query ID.
- Fail phase if JSON parse warning/error occurs.
- Compare by query_id mapping, not file line order.
- Keep active vs archive runs strictly separated.

---

## SECTION 7 - Repo Hygiene Phase (Final Phase Only)

Start only after algorithmic stability is confirmed.

- Identify unused files/modules/imports/configs.
- Identify orphan markdown and duplicate docs.
- Archive first, delete later.
- Verify import resolution, CLI entrypoints, and tests after archive moves.
- Keep restoration manifest for rollback.

---

## SECTION 8 - What Must NOT Be Done

- No new ranking objectives.
- No new diversity heuristics.
- No dynamic budget allocation logic.
- No blind weight tuning.
- No multi-layer edits in one iteration.
- No parallel cleanup tracks.

---

## SECTION 9 - Success Criteria

- Zero unexpected drift in block count.
- Zero unexplained token shrinkage.
- Deterministic ranking/selection behavior across immediate reruns.
- Identical selected block IDs across consecutive verification rerun.
- Judge output integrity maintained (clean, unique, complete).
- Average judge variance across reruns <= 0.2.

---

## SECTION 10 - Execution Order Recommendation

Safest first subsystem: Evaluation/Judge Infrastructure.

Justification:

- Measurement integrity must be trusted before any cleanup decisions.
- Evaluation drift can invalidate all downstream conclusions.
- Fixing this first gives reliable pass/fail gates for every later phase.

Recommended order:

1. Evaluation/Judge Infrastructure
2. Telemetry Emission & Usage
3. Ranking Layer
4. Context Assembly Layer
5. Budget Allocation Logic
6. Retrieval Layer
7. Repository Structural Hygiene

---

Principle: one subsystem, one intent, one verification, one immediate rerun, then proceed or revert.


