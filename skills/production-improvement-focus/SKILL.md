---
name: production-improvement-focus
description: "Use when improving HOM-LLM(v2.0) or similar systems where the priority is broad production-grade quality: accuracy first, then full-distribution safety, simplification, performance, and only then incremental gains. This skill is for choosing and evaluating changes without overfitting, avoiding slice-only promotions, preferring small reversible changes, and treating judge/examine outputs as hints rather than authority."
---

# Production Improvement Focus

Use this skill when working on system-quality improvements, architecture decisions, eval interpretation, or promotion decisions.

## Decision Order
1. Accuracy
2. Broad full-distribution safety
3. Simplification
4. Performance and latency
5. Incremental gain

## Required Rules
- Prefer the smallest change that can improve broad system behavior.
- Prefer simplification or deletion over additive complexity when quality is preserved.
- Do not promote a change from slice evidence alone.
- Use full-20 style broad validation as the promotion gate.
- Do not add query-specific or benchmark-specific behavior.
- Treat judge and examine outputs as hints, not authority.
- Avoid architecture that improves one class of queries by shrinking or damaging the general evidence surface.
- If two options have similar expected quality gain, choose the simpler and faster one.
- Experimental layers must stay isolated from the default answer path until broad validation passes.

## Working Method
1. Identify whether the bottleneck is upstream or downstream:
- query understanding
- retrieval
- ranking
- context assembly
- generation
- evaluation
- operational reliability

2. Before changing behavior, ask:
- Is the change global or only likely to help a narrow slice?
- Can the same gain be achieved with less complexity?
- Is there a cheaper observability or diagnostics step first?
- What is the rollback path if broad quality regresses?

3. Promotion standard:
- direct answer behavior first
- telemetry/artifact evidence second
- judge/examine third
- aggregate scores last

4. Reject changes that:
- depend on query wording
- add routing heuristics tied to benchmark-style phrases
- increase complexity without a clear broad-system reason
- degrade latency materially without high-confidence quality gain

## Practical Biases
- Favor upstream fixes over downstream prompt shaping when the root cause is still uncertain.
- Favor observability before architecture replacement.
- Favor bounded A/B verification over broad speculative rewrites.
- Keep experimental planner/generation paths opt-in until proven safe.

## Repo-Specific Notes
Current broad reference run:
- `eval/runs/warbestbeforecommit`

Current research/plan anchors:
- `imp-help-plan/WORKING_PROTOCOL.md`
- `imp-help-plan/MASTER_IMPROVEMENT_EXECUTION_PLAN.md`
- `imp-help-plan/CONSOLIDATED_DIAGNOSIS_AND_ACTION_STACK_2026-03-10.md`
- `docs/SYSTEM_WIDE_ARCHITECTURAL_REVIEW_ENGINE_2026-03-09.md`

When in doubt:
- choose the safer, simpler, more observable path
- do not spend effort on changes that are unlikely to survive full-20 validation
