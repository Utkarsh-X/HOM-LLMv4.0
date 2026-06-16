import json
from dataclasses import dataclass, field
from pathlib import Path

from homllm_v4.serialization.json import to_jsonable


@dataclass(frozen=True)
class AgentSessionTurn:
    turn_index: int
    query: str
    ask_run_id: str
    ask_stop_reason: str
    answer_text: str
    answer_provider_mode: str
    answer_error_code: str | None
    edit_run_id: str | None
    edit_stop_reason: str | None
    edit_error_code: str | None
    metrics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentSessionState:
    session_id: str
    workspace_root: str
    config_path: str
    artifact_root: str
    instruction: str
    index_built: bool = False
    index_config_path: str | None = None
    index_artifact_paths: dict[str, str] | None = None
    index_metrics: dict[str, object] | None = None
    turns: tuple[AgentSessionTurn, ...] = ()


class AgentSessionStore:
    def __init__(self, *, artifact_root: Path, session_id: str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.session_id = session_id
        self.session_dir = (self.artifact_root / session_id).resolve()
        _ensure_inside(self.session_dir, self.artifact_root)
        self.session_path = self.session_dir / "session.json"

    def create_or_load(
        self,
        *,
        workspace_root: Path,
        config_path: Path,
        instruction: str,
    ) -> AgentSessionState:
        if self.session_path.exists():
            return self.load()
        state = AgentSessionState(
            session_id=self.session_id,
            workspace_root=str(Path(workspace_root).resolve()),
            config_path=str(config_path),
            artifact_root=str(self.artifact_root),
            instruction=instruction,
        )
        self._write(state)
        return state

    def load(self) -> AgentSessionState:
        data = json.loads(self.session_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("session_state_invalid: expected JSON object")
        return _state_from_json(data)

    def append_turn(self, turn: AgentSessionTurn) -> AgentSessionState:
        state = self.load()
        next_turn = (
            turn
            if turn.turn_index == len(state.turns) + 1
            else AgentSessionTurn(
                turn_index=len(state.turns) + 1,
                query=turn.query,
                ask_run_id=turn.ask_run_id,
                ask_stop_reason=turn.ask_stop_reason,
                answer_text=turn.answer_text,
                answer_provider_mode=turn.answer_provider_mode,
                answer_error_code=turn.answer_error_code,
                edit_run_id=turn.edit_run_id,
                edit_stop_reason=turn.edit_stop_reason,
                edit_error_code=turn.edit_error_code,
                metrics=turn.metrics,
            )
        )
        updated = AgentSessionState(
            session_id=state.session_id,
            workspace_root=state.workspace_root,
            config_path=state.config_path,
            artifact_root=state.artifact_root,
            instruction=state.instruction,
            index_built=state.index_built,
            index_config_path=state.index_config_path,
            index_artifact_paths=state.index_artifact_paths,
            index_metrics=state.index_metrics,
            turns=state.turns + (next_turn,),
        )
        self._write(updated)
        return updated

    def update_index_metadata(
        self,
        *,
        index_built: bool,
        index_config_path: str | None,
        index_artifact_paths: dict[str, str] | None,
        index_metrics: dict[str, object] | None,
    ) -> AgentSessionState:
        state = self.load()
        updated = AgentSessionState(
            session_id=state.session_id,
            workspace_root=state.workspace_root,
            config_path=state.config_path,
            artifact_root=state.artifact_root,
            instruction=state.instruction,
            index_built=index_built,
            index_config_path=index_config_path,
            index_artifact_paths=index_artifact_paths,
            index_metrics=index_metrics,
            turns=state.turns,
        )
        self._write(updated)
        return updated

    def _write(self, state: AgentSessionState) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(to_jsonable(state), indent=2, sort_keys=True) + "\n"
        temp_path = self.session_path.with_name(".session.json.tmp")
        temp_path.write_text(text, encoding="utf-8", newline="")
        temp_path.replace(self.session_path)


def _state_from_json(data: dict[str, object]) -> AgentSessionState:
    turns_data = data.get("turns", ())
    if not isinstance(turns_data, list):
        raise ValueError("session_state_invalid: turns must be a list")
    return AgentSessionState(
        session_id=str(data["session_id"]),
        workspace_root=str(data["workspace_root"]),
        config_path=str(data["config_path"]),
        artifact_root=str(data["artifact_root"]),
        instruction=str(data["instruction"]),
        index_built=bool(data.get("index_built", False)),
        index_config_path=_optional_str(data.get("index_config_path")),
        index_artifact_paths=_optional_str_dict(data.get("index_artifact_paths")),
        index_metrics=_optional_dict(data.get("index_metrics")),
        turns=tuple(_turn_from_json(turn) for turn in turns_data),
    )


def _turn_from_json(data: object) -> AgentSessionTurn:
    if not isinstance(data, dict):
        raise ValueError("session_state_invalid: turn must be an object")
    return AgentSessionTurn(
        turn_index=int(data["turn_index"]),
        query=str(data["query"]),
        ask_run_id=str(data["ask_run_id"]),
        ask_stop_reason=str(data["ask_stop_reason"]),
        answer_text=str(data["answer_text"]),
        answer_provider_mode=str(data["answer_provider_mode"]),
        answer_error_code=_optional_str(data.get("answer_error_code")),
        edit_run_id=_optional_str(data.get("edit_run_id")),
        edit_stop_reason=_optional_str(data.get("edit_stop_reason")),
        edit_error_code=_optional_str(data.get("edit_error_code")),
        metrics=_optional_dict(data.get("metrics")) or {},
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_dict(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("session_state_invalid: expected object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError("session_state_invalid: expected string keys")
    return dict(value)


def _optional_str_dict(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    data = _optional_dict(value)
    return {key: str(item) for key, item in (data or {}).items()}


def _ensure_inside(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"session_path_denied: {path}") from exc
