"""
Context Diff - Audit Layer

Pure data types for tracking context modifications.
Every applied action produces exactly one diff entry.

CONSTRAINTS (ABSOLUTE):
- Immutable dataclasses (frozen=True)
- No logic, only bookkeeping
- JSON-serializable
- Deterministic
- No imports from intelligence, generation, retrieval
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Any


# =============================================================================
# DIFF ENTRY
# =============================================================================

@dataclass(frozen=True)
class DiffEntry:
    """
    A single change record in the context diff.
    
    Captures exactly what changed, why, and from which action level.
    Every applied action emits exactly one DiffEntry.
    
    Attributes:
        change_type: What kind of change occurred
        target: The target of the change (block_id, concept, path)
        level: Source level (1, 2, or 3)
        action_type: The action type that caused this change
        reason: Human-readable explanation
        details: Additional structured details (optional)
    """
    
    change_type: Literal["added", "removed", "modified", "reordered", "compacted", "protected", "skipped"]
    target: str  # block_id, concept name, or path
    level: int  # 1, 2, or 3
    action_type: str  # e.g., "DROP", "COMPACT", "PROTECT"
    reason: str  # Human-readable justification
    details: tuple[tuple[str, Any], ...] = ()  # Frozen dict alternative
    
    @property
    def details_dict(self) -> dict[str, Any]:
        """Convert frozen details to dict for display."""
        return dict(self.details)
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "change_type": self.change_type,
            "target": self.target,
            "level": self.level,
            "action_type": self.action_type,
            "reason": self.reason,
            "details": self.details_dict,
        }


# =============================================================================
# CONFLICT RECORD
# =============================================================================

@dataclass(frozen=True)
class ConflictRecord:
    """
    Record of a conflict between actions.
    
    When two actions target the same block with conflicting intents,
    one wins and this record captures what happened.
    """
    
    target: str  # block_id that was contested
    winning_level: int
    winning_action: str
    losing_level: int
    losing_action: str
    resolution_reason: str
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "target": self.target,
            "winning_level": self.winning_level,
            "winning_action": self.winning_action,
            "losing_level": self.losing_level,
            "losing_action": self.losing_action,
            "resolution_reason": self.resolution_reason,
        }


# =============================================================================
# CONTEXT DIFF
# =============================================================================

@dataclass(frozen=True)
class ContextDiff:
    """
    Complete diff of context modifications.
    
    Captures all changes made during plan application.
    Machine-readable and human-inspectable.
    
    Structure:
        ContextDiff
        ├── entries: All individual changes
        ├── conflicts: Recorded conflict resolutions
        └── summary: Aggregate statistics
    
    Guarantees:
    - Every applied action has exactly one entry
    - Conflicts are explicitly recorded
    - Full provenance for debugging
    """
    
    # All change entries
    entries: tuple[DiffEntry, ...]
    
    # Conflict resolutions
    conflicts: tuple[ConflictRecord, ...] = ()
    
    # Summary counts
    blocks_added: int = 0
    blocks_removed: int = 0
    blocks_modified: int = 0
    blocks_reordered: int = 0
    blocks_compacted: int = 0
    blocks_protected: int = 0
    actions_skipped: int = 0
    
    @classmethod
    def empty(cls) -> "ContextDiff":
        """Create an empty diff (no changes)."""
        return cls(
            entries=(),
            conflicts=(),
            blocks_added=0,
            blocks_removed=0,
            blocks_modified=0,
            blocks_reordered=0,
            blocks_compacted=0,
            blocks_protected=0,
            actions_skipped=0,
        )
    
    @property
    def is_empty(self) -> bool:
        """Check if diff contains no entries."""
        return len(self.entries) == 0
    
    @property
    def total_changes(self) -> int:
        """Total number of changes (excluding skipped)."""
        return (
            self.blocks_added +
            self.blocks_removed +
            self.blocks_modified +
            self.blocks_reordered +
            self.blocks_compacted +
            self.blocks_protected
        )
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "entries": [e.to_dict() for e in self.entries],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "summary": {
                "blocks_added": self.blocks_added,
                "blocks_removed": self.blocks_removed,
                "blocks_modified": self.blocks_modified,
                "blocks_reordered": self.blocks_reordered,
                "blocks_compacted": self.blocks_compacted,
                "blocks_protected": self.blocks_protected,
                "actions_skipped": self.actions_skipped,
                "total_changes": self.total_changes,
            },
        }
    
    def pretty_print(self) -> str:
        """Human-readable representation of diff."""
        lines = ["Context Diff Summary:", "=" * 40]
        
        if self.is_empty:
            lines.append("  No changes applied.")
            return "\n".join(lines)
        
        lines.append(f"  Added: {self.blocks_added}")
        lines.append(f"  Removed: {self.blocks_removed}")
        lines.append(f"  Modified: {self.blocks_modified}")
        lines.append(f"  Reordered: {self.blocks_reordered}")
        lines.append(f"  Compacted: {self.blocks_compacted}")
        lines.append(f"  Protected: {self.blocks_protected}")
        lines.append(f"  Skipped: {self.actions_skipped}")
        lines.append("")
        
        if self.conflicts:
            lines.append("Conflicts Resolved:")
            for c in self.conflicts:
                lines.append(f"  {c.target}: L{c.winning_level} {c.winning_action} > L{c.losing_level} {c.losing_action}")
            lines.append("")
        
        lines.append("Entries:")
        for e in self.entries:
            lines.append(f"  [{e.change_type.upper()}] L{e.level} {e.action_type}: {e.target}")
            if e.reason:
                lines.append(f"    Reason: {e.reason}")
        
        return "\n".join(lines)


# =============================================================================
# DIFF BUILDER
# =============================================================================

class DiffBuilder:
    """
    Mutable builder for constructing ContextDiff.
    
    Used internally by ContextApplier to accumulate changes.
    Produces an immutable ContextDiff when finalized.
    
    This is the ONLY mutable class in this module.
    """
    
    def __init__(self):
        """Initialize empty builder."""
        self._entries: list[DiffEntry] = []
        self._conflicts: list[ConflictRecord] = []
        self._counts = {
            "added": 0,
            "removed": 0,
            "modified": 0,
            "reordered": 0,
            "compacted": 0,
            "protected": 0,
            "skipped": 0,
        }
    
    def add_entry(
        self,
        change_type: str,
        target: str,
        level: int,
        action_type: str,
        reason: str,
        details: dict | None = None,
    ) -> None:
        """
        Add a diff entry.
        
        Args:
            change_type: Type of change
            target: Target block_id or identifier
            level: Source level (1, 2, or 3)
            action_type: Action that caused the change
            reason: Human-readable explanation
            details: Optional additional details
        """
        frozen_details = tuple((k, v) for k, v in (details or {}).items())
        
        entry = DiffEntry(
            change_type=change_type,  # type: ignore
            target=target,
            level=level,
            action_type=action_type,
            reason=reason,
            details=frozen_details,
        )
        
        self._entries.append(entry)
        
        # Update counts
        if change_type in self._counts:
            self._counts[change_type] += 1
    
    def add_conflict(
        self,
        target: str,
        winning_level: int,
        winning_action: str,
        losing_level: int,
        losing_action: str,
        resolution_reason: str,
    ) -> None:
        """Record a conflict resolution."""
        self._conflicts.append(ConflictRecord(
            target=target,
            winning_level=winning_level,
            winning_action=winning_action,
            losing_level=losing_level,
            losing_action=losing_action,
            resolution_reason=resolution_reason,
        ))
    
    def build(self) -> ContextDiff:
        """Build immutable ContextDiff from accumulated entries."""
        return ContextDiff(
            entries=tuple(self._entries),
            conflicts=tuple(self._conflicts),
            blocks_added=self._counts["added"],
            blocks_removed=self._counts["removed"],
            blocks_modified=self._counts["modified"],
            blocks_reordered=self._counts["reordered"],
            blocks_compacted=self._counts["compacted"],
            blocks_protected=self._counts["protected"],
            actions_skipped=self._counts["skipped"],
        )


__all__ = [
    "DiffEntry",
    "ConflictRecord",
    "ContextDiff",
    "DiffBuilder",
]
