import json
from pathlib import Path

import pytest

from homllm_v4.runtime.session_state import (
    AgentSessionStore,
    AgentSessionTurn,
)


def test_session_store_creates_loads_and_appends_turns(tmp_path: Path) -> None:
    store = AgentSessionStore(
        artifact_root=tmp_path / "runs",
        session_id="session-1",
    )

    state = store.create_or_load(
        workspace_root=tmp_path / "workspace",
        config_path=Path("config.yaml"),
        instruction="Fix and verify normalize_sku.",
    )

    assert state.session_id == "session-1"
    assert state.workspace_root == str((tmp_path / "workspace").resolve())
    assert state.config_path == str(Path("config.yaml"))
    assert state.instruction == "Fix and verify normalize_sku."
    assert state.turns == ()
    assert store.session_path.is_file()

    first_turn = AgentSessionTurn(
        turn_index=1,
        query="Where is normalize_sku?",
        ask_run_id="session-1-ask",
        ask_stop_reason="sufficient",
        answer_text="normalize_sku is in inventory/items.py",
        answer_provider_mode="live",
        answer_error_code=None,
        edit_run_id=None,
        edit_stop_reason=None,
        edit_error_code=None,
        metrics={"provider_tokens_in": 10},
    )
    updated = store.append_turn(first_turn)

    assert len(updated.turns) == 1
    assert updated.turns[0].turn_index == 1
    assert updated.turns[0].metrics["provider_tokens_in"] == 10

    reloaded = AgentSessionStore(
        artifact_root=tmp_path / "runs",
        session_id="session-1",
    ).create_or_load(
        workspace_root=tmp_path / "workspace",
        config_path=Path("ignored.yaml"),
        instruction="ignored on load",
    )

    assert reloaded.instruction == "Fix and verify normalize_sku."
    assert len(reloaded.turns) == 1
    assert reloaded.turns[0].answer_text == "normalize_sku is in inventory/items.py"
    payload = json.loads(store.session_path.read_text(encoding="utf-8"))
    assert payload["turns"][0]["ask_run_id"] == "session-1-ask"


def test_session_store_rejects_session_id_that_escapes_artifact_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="session_path_denied"):
        AgentSessionStore(
            artifact_root=tmp_path / "runs",
            session_id="../escape",
        )


def test_session_store_updates_index_metadata(tmp_path: Path) -> None:
    store = AgentSessionStore(
        artifact_root=tmp_path / "runs",
        session_id="session-index",
    )
    store.create_or_load(
        workspace_root=tmp_path / "workspace",
        config_path=Path("config.yaml"),
        instruction="Index then answer.",
    )

    updated = store.update_index_metadata(
        index_built=True,
        index_config_path=str(tmp_path / "runs" / "session-index" / "index" / "generated_config.yaml"),
        index_artifact_paths={"duckdb": "index/metadata.duckdb"},
        index_metrics={"source_file_count": 6},
    )

    assert updated.index_built is True
    assert updated.index_config_path.endswith("generated_config.yaml")
    assert updated.index_artifact_paths == {"duckdb": "index/metadata.duckdb"}
    assert updated.index_metrics == {"source_file_count": 6}

    reloaded = store.load()
    assert reloaded.index_built is True
    assert reloaded.index_metrics == {"source_file_count": 6}
