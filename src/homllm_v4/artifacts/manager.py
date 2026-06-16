import hashlib
import json
from pathlib import Path

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.serialization.json import to_jsonable


class ArtifactManager:
    def __init__(self, *, workspace_root: Path, artifact_root: Path | None = None) -> None:
        self.workspace_root = workspace_root.resolve()
        self.artifact_root = (artifact_root or self.workspace_root / ".homllm" / "runs").resolve()
        self._run_dir: Path | None = None

    @property
    def run_dir(self) -> Path:
        if self._run_dir is None:
            raise ValueError("artifact_write_failed: run has not been created")
        return self._run_dir

    def create_run(self, run_id: str, metadata: dict[str, object]) -> None:
        run_dir = (self.artifact_root / run_id).resolve()
        self._ensure_inside(run_dir, self.artifact_root)
        self._run_dir = run_dir

        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("snapshots", "evidence", "context", "commands", "patches", "verification", "response"):
            (run_dir / name).mkdir(exist_ok=True)

        self._write_json_atomic(run_dir / "metadata.json", metadata)
        self._write_json_atomic(run_dir / "task.json", {})
        (run_dir / "events.jsonl").touch(exist_ok=True)

    def write_json(
        self,
        relative_path: str,
        payload: object,
        artifact_type: str,
        description: str,
    ) -> ArtifactRef:
        path = self.resolve_artifact_path(relative_path)
        self._write_json_atomic(path, payload)
        return self._artifact_ref(path, artifact_type, description)

    def write_text(
        self,
        relative_path: str,
        text: str,
        artifact_type: str,
        description: str,
    ) -> ArtifactRef:
        path = self.resolve_artifact_path(relative_path)
        self._write_text_atomic(path, text)
        return self._artifact_ref(path, artifact_type, description)

    def resolve_artifact_path(self, relative_path: str) -> Path:
        path = (self.run_dir / relative_path).resolve()
        self._ensure_inside(path, self.run_dir)
        return path

    def _artifact_ref(self, path: Path, artifact_type: str, description: str) -> ArtifactRef:
        text = path.read_text(encoding="utf-8")
        return ArtifactRef(
            artifact_type=artifact_type,
            path=self._display_path(path),
            description=description,
            content_hash=self._sha256_text(text),
        )

    def _display_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(self.workspace_root).as_posix()
        except ValueError:
            return str(resolved)

    @staticmethod
    def _write_json_atomic(path: Path, payload: object) -> None:
        text = json.dumps(to_jsonable(payload), indent=2, sort_keys=True) + "\n"
        ArtifactManager._write_text_atomic(path, text)

    @staticmethod
    def _write_text_atomic(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_text(text, encoding="utf-8", newline="")
        temp_path.replace(path)

    @staticmethod
    def _sha256_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @staticmethod
    def _ensure_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path_denied: {path}") from exc
