from pathlib import Path
from uuid import uuid4

from homllm_v4.adapters.v3_read_only_factory import build_v3_read_only_components
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.loop import ReadOnlyLoopRequest, ReadOnlyLoopResult
from homllm_v4.contracts.policy import read_only_milestone1_policy
from homllm_v4.evaluation.fixture_suites import (
    run_python_patch_fixture_suite,
    run_python_provider_patch_fixture_suite,
)
from homllm_v4.evaluation.agent_benchmark import (
    AgentBenchmarkCase,
    INTERNAL_AGENT_BENCHMARK_CASES,
    agent_benchmark_case_metadata,
    run_homllm_agent_benchmark,
)
from homllm_v4.evaluation.real_index_provider_suites import run_real_index_provider_patch_suite
from homllm_v4.evaluation.real_index_provider_suites import real_index_provider_patch_case_metadata
from homllm_v4.evaluation.swebench_lite_suites import (
    SwebenchLiteFixture,
    load_swebench_lite_fixtures,
    swebench_lite_case_metadata,
    swebench_lite_cases,
)
from homllm_v4.evaluation.token_efficiency import (
    TokenEfficiencyCaseResult,
    TokenEfficiencyRunResult,
    run_token_efficiency_comparison,
)
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.runtime.agent_task import AgentTaskRequest, AgentTaskResult, run_agent_task
from homllm_v4.runtime.agent_run import (
    HomllmAgentRunRequest,
    HomllmAgentRunResult,
    run_homllm_agent,
)
from homllm_v4.runtime.agent_session import (
    AgentSessionRequest,
    AgentSessionResult,
    run_agent_session,
)
from homllm_v4.runtime.grounded_answer import (
    GroundedAnswerRequest,
    GroundedAnswerResult,
    GroundedAnswerSynthesizer,
)
from homllm_v4.runtime.session_state import (
    AgentSessionState,
    AgentSessionStore,
    AgentSessionTurn,
)
from homllm_v4.runtime.read_only_loop import ReadOnlyMultipassLoop


def run_read_only_query(
    *,
    config_path: Path,
    workspace_root: Path,
    query: str,
    run_id: str | None = None,
    artifact_root: Path | None = None,
    max_passes: int = 1,
    smoke_safe: bool = True,
    component_builder=build_v3_read_only_components,
) -> ReadOnlyLoopResult:
    resolved_run_id = run_id or str(uuid4())
    resolved_workspace = Path(workspace_root).resolve()
    resolved_artifact_root = (
        Path(artifact_root).resolve()
        if artifact_root is not None
        else resolved_workspace / ".homllm" / "runs"
    )
    components = component_builder(Path(config_path), smoke_safe=smoke_safe)
    artifact_manager = ArtifactManager(
        workspace_root=resolved_workspace,
        artifact_root=resolved_artifact_root,
    )
    artifact_manager.create_run(
        resolved_run_id,
        {
            "entrypoint": "homllm_v4.api.run_read_only_query",
            "query": query,
        },
    )
    event_writer = EventWriter(resolved_artifact_root / resolved_run_id / "events.jsonl")
    loop = ReadOnlyMultipassLoop(
        service_registry=components.service_registry,
        artifact_manager=artifact_manager,
        event_writer=event_writer,
        policy=read_only_milestone1_policy(),
    )
    return loop.run(
        ReadOnlyLoopRequest(
            task_id=f"{resolved_run_id}:read-only",
            run_id=resolved_run_id,
            workspace_root=str(resolved_workspace),
            query=query,
            max_passes=max_passes,
            index_artifact_paths=components.index_artifact_paths,
        )
    )
