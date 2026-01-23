"""
Output formatters for diagnostic reports.

Supports: terminal, JSON, Markdown outputs.
All formats are deterministic and machine-parseable.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any
from pathlib import Path


@dataclass
class DiagnosticResult:
    """Base diagnostic result structure."""
    
    phase: str
    query_id: str | int | None
    run_id: str | None
    summary: dict[str, Any]
    details: list[dict[str, Any]]
    warnings: list[str]
    

class BaseFormatter(ABC):
    """Abstract base for output formatters."""
    
    @abstractmethod
    def format(self, result: DiagnosticResult) -> str:
        """Format a diagnostic result."""
        ...
    
    @abstractmethod
    def format_summary(self, results: list[DiagnosticResult]) -> str:
        """Format aggregated summary of multiple results."""
        ...
    
    def save(self, content: str, filepath: Path) -> None:
        """Save formatted content to file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)


class TerminalFormatter(BaseFormatter):
    """
    Human-readable terminal output.
    
    Requirements:
    - No ANSI clutter (no color codes)
    - No emojis (single Unicode warning symbol allowed)
    - No verbosity fluff
    - Structured, deterministic
    """
    
    def format(self, result: DiagnosticResult) -> str:
        """Format a single diagnostic result for terminal."""
        lines = []
        
        # Header
        lines.append(f"[{result.phase.upper()} DIAGNOSTIC]")
        if result.query_id is not None:
            lines.append(f"Query ID: {result.query_id:02d}" if isinstance(result.query_id, int) else f"Query ID: {result.query_id}")
        if result.run_id:
            lines.append(f"Run ID: {result.run_id}")
        lines.append("")
        
        # Summary
        for key, value in result.summary.items():
            formatted_key = key.replace("_", " ").title()
            lines.append(f"{formatted_key}: {self._format_value(value)}")
        
        lines.append("")
        
        # Warnings
        if result.warnings:
            for warning in result.warnings:
                lines.append(f"! {warning}")
            lines.append("")
        
        # Details (top 5 by default)
        if result.details:
            lines.append("Top entries:")
            for i, detail in enumerate(result.details[:5]):
                detail_str = ", ".join(f"{k}={self._format_value(v)}" for k, v in detail.items())
                lines.append(f"  {i+1}. {detail_str}")
        
        return "\n".join(lines)
    
    def format_summary(self, results: list[DiagnosticResult]) -> str:
        """Format aggregated summary."""
        lines = ["[DIAGNOSTIC SUMMARY]", ""]
        
        for result in results:
            lines.append(f"Phase: {result.phase.upper()}")
            for key, value in result.summary.items():
                formatted_key = key.replace("_", " ").title()
                lines.append(f"  {formatted_key}: {self._format_value(value)}")
            lines.append("")
        
        # Aggregate warnings
        all_warnings = []
        for result in results:
            all_warnings.extend(result.warnings)
        
        if all_warnings:
            lines.append("Warnings:")
            for warning in all_warnings:
                lines.append(f"  ! {warning}")
        
        return "\n".join(lines)
    
    def _format_value(self, value: Any) -> str:
        """Format a value for terminal display."""
        if isinstance(value, float):
            return f"{value:.2f}" if value >= 0.01 else f"{value:.4f}"
        if isinstance(value, (list, tuple)):
            return str(len(value)) + " items" if len(value) > 3 else str(list(value))
        return str(value)


class JsonFormatter(BaseFormatter):
    """
    Machine-readable JSON output.
    
    Requirements:
    - Valid JSON
    - Deterministic key ordering
    - No pretty-printing by default (compact)
    """
    
    def __init__(self, pretty: bool = False):
        self.pretty = pretty
    
    def format(self, result: DiagnosticResult) -> str:
        """Format a single diagnostic result as JSON."""
        data = {
            "phase": result.phase,
            "query_id": result.query_id,
            "run_id": result.run_id,
            "summary": result.summary,
            "details": result.details,
            "warnings": result.warnings,
        }
        
        if self.pretty:
            return json.dumps(data, indent=2, sort_keys=True, default=str)
        return json.dumps(data, sort_keys=True, default=str)
    
    def format_summary(self, results: list[DiagnosticResult]) -> str:
        """Format aggregated summary as JSON."""
        data = {
            "results": [
                {
                    "phase": r.phase,
                    "summary": r.summary,
                    "warning_count": len(r.warnings),
                }
                for r in results
            ],
            "total_warnings": sum(len(r.warnings) for r in results),
        }
        
        if self.pretty:
            return json.dumps(data, indent=2, sort_keys=True, default=str)
        return json.dumps(data, sort_keys=True, default=str)


class MarkdownFormatter(BaseFormatter):
    """
    Human-readable Markdown output.
    
    For documentation and analysis reports.
    """
    
    def format(self, result: DiagnosticResult) -> str:
        """Format a single diagnostic result as Markdown."""
        lines = []
        
        # Header
        lines.append(f"# {result.phase.upper()} Diagnostic Report")
        lines.append("")
        
        if result.query_id is not None:
            lines.append(f"**Query ID**: {result.query_id}")
        if result.run_id:
            lines.append(f"**Run ID**: `{result.run_id}`")
        lines.append("")
        
        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, value in result.summary.items():
            formatted_key = key.replace("_", " ").title()
            lines.append(f"| {formatted_key} | {self._format_value(value)} |")
        lines.append("")
        
        # Warnings
        if result.warnings:
            lines.append("## Warnings")
            lines.append("")
            for warning in result.warnings:
                lines.append(f"- {warning}")
            lines.append("")
        
        # Details
        if result.details:
            lines.append("## Details")
            lines.append("")
            lines.append("| # | " + " | ".join(result.details[0].keys()) + " |")
            lines.append("| --- | " + " | ".join("---" for _ in result.details[0].keys()) + " |")
            for i, detail in enumerate(result.details[:10]):
                values = [self._format_value(v) for v in detail.values()]
                lines.append(f"| {i+1} | " + " | ".join(values) + " |")
        
        return "\n".join(lines)
    
    def format_summary(self, results: list[DiagnosticResult]) -> str:
        """Format aggregated summary as Markdown."""
        lines = ["# Diagnostic Summary Report", ""]
        
        for result in results:
            lines.append(f"## {result.phase.upper()}")
            lines.append("")
            for key, value in result.summary.items():
                formatted_key = key.replace("_", " ").title()
                lines.append(f"- **{formatted_key}**: {self._format_value(value)}")
            lines.append("")
        
        # Aggregate warnings
        all_warnings = []
        for result in results:
            for warning in result.warnings:
                all_warnings.append((result.phase, warning))
        
        if all_warnings:
            lines.append("## All Warnings")
            lines.append("")
            for phase, warning in all_warnings:
                lines.append(f"- [{phase}] {warning}")
        
        return "\n".join(lines)
    
    def _format_value(self, value: Any) -> str:
        """Format a value for Markdown display."""
        if isinstance(value, float):
            return f"{value:.2f}" if value >= 0.01 else f"{value:.4f}"
        if isinstance(value, str) and "/" in value:
            return f"`{value}`"  # File paths
        return str(value)
