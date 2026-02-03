"""
Diagnostics Runner — read-only diagnostic entry point.

Runs the L1–L3 diagnostic pipeline only. All action engines (level1/2/3) are
disabled: no context mutation, no action proposals, no prompt injection, no loops.
Produces a single DiagnosticSnapshot for observation and testing.

Usage:
    from homllm.intelligence.diagnostics_runner import run_diagnostics
    snapshot = run_diagnostics(context_artifact)
    if snapshot:
        # snapshot.level1, .level2, .level3 populated
        ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from homllm.intelligence.controller import create_intelligence_controller
from homllm.intelligence.diagnostics.controller import (
    DiagnosticController,
    create_diagnostic_provider,
)
from homllm.intelligence.interfaces import DiagnosticSnapshot

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Global toggle: can later be driven by config
# -----------------------------------------------------------------------------
DIAGNOSTICS_ENABLED: bool = True


def run_diagnostics(
    context: "ContextArtifact",
    *,
    force_run: bool = False,
) -> Optional[DiagnosticSnapshot]:
    """
    Run the read-only diagnostic pipeline on a context artifact.

    - Runs only diagnostics (L1 per-block, L2 relational/gaps, L3 summary/intent/roles/load/failure_mode).
    - All action engines are disabled (level1_enabled=False, level2_enabled=False, level3_enabled=False).
    - Does not mutate context, propose actions, or inject prompts.

    Args:
        context: ContextArtifact to analyze (read-only).
        force_run: If True, run even when DIAGNOSTICS_ENABLED is False, and re-raise on failure.

    Returns:
        DiagnosticSnapshot with L1/L2/L3 populated, or None if disabled or on failure
        (unless force_run=True, in which case failures are re-raised).
    """
    if not DIAGNOSTICS_ENABLED and not force_run:
        logger.debug("Diagnostics disabled; returning None.")
        return None

    # Same diagnostic provider the controller uses; all action engines disabled.
    diagnostic_controller: DiagnosticController = create_diagnostic_provider()
    _ = create_intelligence_controller(
        diagnostic_controller=diagnostic_controller,
        level1_enabled=False,
        level2_enabled=False,
        level3_enabled=False,
        audit_enabled=False,
        assertion_readability_enabled=False,
    )
    # We run only the diagnostic pipeline below; we do not call controller.run().

    try:
        logger.debug("Running diagnostic pipeline (L1/L2/L3) on context.")
        snapshot = diagnostic_controller.analyze(context)
        logger.info(
            "Diagnostics complete: L1=%s, L2=%s, L3=%s",
            snapshot.level1.status,
            snapshot.level2.status,
            snapshot.level3.status,
        )
        return snapshot
    except Exception as e:
        logger.warning("Diagnostic pipeline failed: %s", e, exc_info=True)
        if force_run:
            raise
        return None


# -----------------------------------------------------------------------------
# Usage example (for reference; do not execute as main)
# -----------------------------------------------------------------------------
#
# from homllm.context.interfaces import ContextArtifact
# from homllm.intelligence.diagnostics_runner import run_diagnostics, DIAGNOSTICS_ENABLED
#
# def example(context: ContextArtifact) -> None:
#     if not DIAGNOSTICS_ENABLED:
#         return
#     snapshot = run_diagnostics(context)
#     if snapshot is None:
#         return  # disabled or failed
#     # Inspect snapshot.level1.blocks, snapshot.level2.result, snapshot.level3.result
#     # Context token count is unchanged; no actions applied.
#
# # Force run for tests (bypasses global toggle, re-raises on error):
# snapshot = run_diagnostics(context, force_run=True)
