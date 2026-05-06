# HOM-LLM North Star and Validation Plan

## Purpose

HOM-LLM should be developed as a token-efficient, evidence-first coding agent. Its core advantage should remain the existing retrieval, ranking, context assembly, and grounded generation stack. Agentic capabilities should be added only where they improve task completion, verification, or user value.

This plan does not abandon the production-grade product ambition. It protects that ambition by requiring each phase to earn the next one through measurable evidence.

## North Star

Build a production-capable coding assistant that uses advanced code RAG as its primary substrate and invokes planning, execution, patching, and verification only when needed.

The central thesis is:

Can a RAG-first coding agent solve repository tasks with fewer tokens, less wandering, and stronger grounding than generic agent loops?

The product ambition is:

If the thesis proves useful, package HOM-LLM into a developer-facing coding assistant that can answer, debug, patch, verify, and explain repository changes safely and economically.

## Non-Goals

- Do not try to beat every coding agent on every task class.
- Do not clone generic autonomous coding agents.
- Do not make agentic behavior the default path for simple repository questions.
- Do not add write-capable behavior before verification and execution are stable.
- Do not optimize for benchmark optics before the system can solve real tasks reliably.

## Strategic Position

HOM-LLM should compete by being evidence-first, not by being more autonomous. Generic agents often spend large token budgets searching, reading, retrying, and drifting. HOM-LLM should reduce that waste by using deterministic evidence acquisition before expensive reasoning or tool use.

The intended advantage is not raw autonomy. The intended advantage is disciplined evidence selection plus bounded action.

## Validation Ladder

### Stage 1: Read-Only Agentic Stabilization

Goal: prove that bounded multi-pass evidence acquisition improves hard code understanding tasks without regressing simple tasks.

Required capabilities:

- route simple tasks to single-pass mode
- route complex tasks to read-only agentic mode
- preserve retrieval, ranking, and context assembly as the main evidence path
- record structured traces for every orchestration pass
- measure regressions, latency, and token overhead

Exit criteria:

- read-only agentic mode beats or matches the current baseline on selected hard tasks
- simple explain/search tasks do not regress
- known regressions are understood and either fixed or explicitly accepted

### Stage 2: Verification-First Execution

Goal: let the system verify claims and task outcomes without modifying files.

Required capabilities:

- run safe allowlisted commands for tests, lint, build checks, and inspection
- produce structured command traces
- reject success states when verification fails
- cap repeated failures and surface them clearly

Exit criteria:

- the system can use execution evidence to confirm or reject answers
- failed checks become actionable feedback, not hidden errors
- no destructive command path is available by default

### Stage 3: Patch-Capable Mode

Goal: support controlled repository edits with post-change verification.

Required capabilities:

- apply structured patches
- protect against stale context
- preserve diff manifests
- require post-patch verification before success
- explain what changed and why

Exit criteria:

- the system can complete small coding tasks end to end
- tests or targeted verification commands pass for completed patches
- unsupported or risky edits are rejected instead of forced

### Stage 4: Internal Benchmarking

Goal: validate HOM-LLM on cheap, controlled, repeatable tasks before public benchmark runs.

Benchmark set:

- 20 repository Q&A tasks
- 10 debugging or explanation tasks requiring evidence synthesis
- 10 small patch tasks with tests or deterministic checks
- selected regression tasks from previous failed canaries

Metrics:

- task success
- factual grounding
- patch correctness
- test pass rate
- token usage
- latency
- number of tool calls
- repeated loop count
- user-facing clarity

Exit criteria:

- clear task class where HOM-LLM has an advantage
- known failure classes are documented
- cost and latency are acceptable enough for small public benchmark attempts

### Stage 5: Public Benchmark Probing

Goal: understand where HOM-LLM stands against external benchmark tasks.

Initial targets:

- small SWE-bench Lite or SWE-bench Verified subset for patch tasks
- small Terminal-Bench subset for terminal/tool-use tasks

Rules:

- run in small batches
- track cost per solved task
- compare against generic agent behavior where possible
- prefer failure analysis over leaderboard chasing

Exit criteria:

- evidence shows whether the RAG-first approach transfers beyond the internal repo
- the system has a credible path to broader benchmark coverage or the limits are clear

## Product Path

Production-grade product work should start only after the core loop proves useful. Productization should include:

- reliable local setup
- repository indexing workflow
- configuration presets
- usable CLI or UI
- audit traces
- cost controls
- permission controls
- test and patch workflow
- clear documentation
- failure recovery and supportability

The product goal remains alive, but it is conditional. Each phase must earn the next phase.

## Decision Rules

Proceed when:

- measurable quality improves
- token cost is justified by task quality
- verification blocks incorrect success claims
- the system keeps retrieval as its evidence backbone
- users can understand why an answer or patch was produced

Pause or redesign when:

- agentic loops increase token cost without quality gains
- simple tasks regress against single-pass mode
- verification becomes ceremonial
- patching produces changes that cannot be tested or explained
- benchmarks reveal no task class where HOM-LLM has a plausible advantage

## Immediate Next Milestone

The next milestone is:

Read-only agentic orchestration v1 is clean, measured, and non-regressing.

Implementation focus:

- extract routing and orchestration out of `runtime/run_query.py`
- create `src/homllm/agent/router.py`
- create `src/homllm/agent/orchestrator.py`
- keep `runtime/run_query.py` as the stable baseline path
- fix or explain the known read-only agentic regressions
- preserve structured telemetry for every run

## Current Known Regressions To Analyze

The latest inspected full canary showed strong performance but not clean enough for promotion:

- 16 improved
- 1 equal
- 3 regressed

The regressed query classes were:

- partial failure and at-least-once semantics
- optimizer rule synthesis with timing and plan caching
- stress test outcome synthesis

Likely failure pattern:

The agentic path sometimes produces more generic or less synthesized answers. The fix should not be more autonomy by default. The fix should be better sufficiency, synthesis, and verification gates.

## Working Principle

Hope is allowed, but each phase must convert hope into evidence.

