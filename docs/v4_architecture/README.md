# HOM-LLM v4 Architecture Workspace

This directory is for architecture discovery, design, audits, runbooks, and
milestone findings.

No v4 implementation should begin until the architecture documents answer:

- What parts of v3 are reusable as stable services?
- What parts of v3 are useful only as references?
- What parts of v3 should not be carried forward?
- What are the typed tool contracts for read, retrieve, write, execute, verify, and patch operations?
- What are the stop rules, permission boundaries, and verification gates?
- What must be proven by evaluation before v4 becomes a product track?

## Working Rule

HOM-LLM v4 should not be a rushed rewrite. It should be a clean architecture that preserves the hard-won retrieval, ranking, context, diagnostics, and evaluation lessons from v3 while removing the single-pass/read-only assumptions that constrain the current design.

## Document Order

**Design phase (01–06):**

1. `01-current-system-asset-map.md`
   - Map v3 components into reuse, wrap, rewrite, or discard decisions.

2. `02-v4-first-principles-architecture.md`
   - Define the target system from first principles.

3. `03-tool-and-service-contracts.md`
   - Specify typed tools, permissions, telemetry, and failure modes.

4. `04-agent-loop-and-memory-design.md`
   - Specify multi-pass planning, working memory, stop rules, and state transitions.

5. `05-write-execute-verify-design.md`
   - Specify safe patching, execution, verification, rollback, and completion gates.

6. `06-migration-and-validation-plan.md`
   - Specify how v4 is built beside v3, evaluated, and promoted.

**Implementation phase (07–09):**

7. `07-milestone-1-implementation-spec.md`
   - Narrow Milestone 1 into concrete package, contract, adapter, artifact, and test requirements.

8. `08-milestone-1-4-implementation-audit.md`
   - Audit the implemented v4 foundation against Milestone 1-4 exit criteria and record remaining gaps.

9. `09-active-goal-completion-audit.md`
   - Comprehensive prompt-to-artifact checklist audit of the MVP agent build-out (through M5, provider integration, planning, benchmarking).

**Execution & validation phase (10–13):**

10. `10-mvp-agent-runbook.md`
    - Every runnable command, staged from deterministic regressions (no API
      key) to live SWE-bench Lite windows; includes §7 on the strict corpus,
      materialization, staged campaigns, and mid-session checkups.

11. `11-swebench-live-milestone-findings.md`
    - Earlier live findings against `gemini-3.5-flash-lite` (0/4 verified;
      failure-mode taxonomy that motivated the agentic upgrade).

12. `12-agentic-loop-upgrade-plan.md`
    - The bounded agentic tool loop plan (Milestones A/B/C) — **all complete**;
      includes the seed-evidence extraction, action contract, and the
      validation-milestone scope.

13. `13-progress-review-and-benchmark-state.md`
    - **Current status document** (2026-09-11): what is built and proven, the
      SWE-bench Lite campaign chronology and scoreboard, uncommitted work,
      and ordered next actions. Start here for "where does the project stand."

14. `14-competitiveness-research-frontier-agents.md`
    - **Research & strategy** (2026-09-12): landscape survey of frontier
      coding-agent harnesses (SWE-Effi, KGCompass, RepoGraph, RepoMem,
      mini-SWE-agent, ACI ablations), a v4 gap analysis against that
      evidence, a prioritized P0-P7 proposal backlog with measurement gates
      for each item, and explicit anti-recommendations. Proposals only -
      nothing binds until separately planned and measured.

15. `15-code-level-research-findings.md`
    - **Code-level research** (2026-09-12): implementation-level findings
      F-01..F-13 with file anchors and live-run evidence - transcript
      snowball mechanics, seed-evidence narrowing, the single-file patch
      ceiling, repair-loop cold starts, P2P never verified by the live
      campaign, and the empty flagship events ledger. Updates the doc-14
      backlog (new P0b harness-integrity item and P8 multi-file ceiling)
      and adds a pre-campaign checklist. Proposals only - nothing binds
      until separately planned and measured.

Also in this directory:

- `11-swebench-validation-findings.md` (second file with the `11-` prefix)
  — the SWE-bench Lite harness certification record: materializer shims,
  gold-patch validation, verdict-ownership audit, orchestrator hardening,
  and the staged long-run guide. Companion to doc 13.
