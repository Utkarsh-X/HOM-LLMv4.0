from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactRef:
    artifact_type: str
    path: str
    description: str
    content_hash: str | None
