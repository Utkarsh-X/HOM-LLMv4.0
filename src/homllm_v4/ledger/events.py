from dataclasses import dataclass, field

from homllm_v4.contracts.artifacts import ArtifactRef

RUN_STARTED = "run_started"
POLICY_CREATED = "policy_created"
ARTIFACT_WRITTEN = "artifact_written"
LOOP_PASS_STARTED = "loop_pass_started"
INDEX_VALIDATED = "index_validated"
RETRIEVAL_COMPLETED = "retrieval_completed"
RANKING_COMPLETED = "ranking_completed"
CONTEXT_COMPLETED = "context_completed"
SUFFICIENCY_DECIDED = "sufficiency_decided"
REPEATED_STATE_DETECTED = "repeated_state_detected"
PATCH_ATTEMPTED = "patch_attempted"
PATCH_COMPLETED = "patch_completed"
PATCH_ROLLED_BACK = "patch_rolled_back"
REPAIR_ATTEMPTED = "repair_attempted"
VERIFICATION_COMPLETED = "verification_completed"
SERVICE_FAILED = "service_failed"
RUN_COMPLETED = "run_completed"


@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    task_id: str
    phase: str
    event_type: str
    timestamp: str
    summary: dict[str, object] = field(default_factory=dict)
    artifact_refs: tuple[ArtifactRef, ...] = field(default_factory=tuple)
