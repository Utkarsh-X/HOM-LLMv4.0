"""
Context Assembly Diagnostics (HIGHEST PRIORITY)

Explains: Why did the model see *this* and not *that*?

For every selected block:
- block_id
- source (file / symbol)
- origin phase (BM25 / vector / expansion)
- token count
- semantic score
- structural score
- final score
- position in context

Derived signals:
- Token concentration (top-X blocks)
- Redundancy detection (semantic similarity)
- Structural vs semantic dominance ratio
- Dropped blocks due to budget
- Context entropy score (signal vs noise)

Intra-Block Diagnostics (STEP 2):
- Token composition (comments, imports, signatures, control-flow, docstrings)
- Identifier density (unique identifiers, top repeated)
- Structural payload (functions, classes, methods)
- Redundancy hints (repeated patterns, error-handling, logging)

Read-only: Never modifies core system artifacts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import json
import statistics
import re
from collections import Counter

from diagnostics.common.formatters import DiagnosticResult
from diagnostics.common.utils import safe_divide, compute_percentile


# ============================================================================
# INTRA-BLOCK DIAGNOSTICS (STEP 2)
# ============================================================================

@dataclass
class TokenBreakdown:
    """Token composition breakdown for a block."""
    
    code_logic_pct: float = 0.0
    comments_pct: float = 0.0
    error_handling_pct: float = 0.0
    logging_pct: float = 0.0
    imports_boiler_pct: float = 0.0
    docstrings_pct: float = 0.0
    signatures_pct: float = 0.0
    control_flow_pct: float = 0.0
    whitespace_pct: float = 0.0
    
    # Raw line counts for reference
    total_lines: int = 0
    comment_lines: int = 0
    import_lines: int = 0
    docstring_lines: int = 0
    error_lines: int = 0
    logging_lines: int = 0
    control_flow_lines: int = 0
    signature_lines: int = 0
    code_lines: int = 0


@dataclass 
class IdentifierDensity:
    """Identifier density analysis for a block."""
    
    total_unique: int = 0
    top_repeated: list[tuple[str, int]] = field(default_factory=list)  # (identifier, count)
    density_ratio: float = 0.0  # unique identifiers / total tokens


@dataclass
class StructuralPayload:
    """Structural content of a block."""
    
    function_count: int = 0
    class_count: int = 0
    method_count: int = 0
    decorator_count: int = 0
    nested_depth_max: int = 0


@dataclass
class RedundancyHints:
    """Redundancy detection for a block."""
    
    repeated_patterns: list[str] = field(default_factory=list)  # Pattern descriptions
    error_handling_blocks: int = 0
    logging_calls: int = 0
    has_repeated_logging: bool = False
    has_repeated_error_handling: bool = False
    boilerplate_score: float = 0.0  # 0.0 to 1.0, higher = more boilerplate


@dataclass
class IntraBlockDiagnostic:
    """Complete intra-block diagnostic for a single block."""
    
    block_id: str
    file: str
    symbol: str
    tokens: int
    
    # Composition breakdown
    token_breakdown: TokenBreakdown = field(default_factory=TokenBreakdown)
    
    # Identifier analysis
    identifier_density: IdentifierDensity = field(default_factory=IdentifierDensity)
    
    # Structural payload
    structural_payload: StructuralPayload = field(default_factory=StructuralPayload)
    
    # Redundancy
    redundancy_hints: RedundancyHints = field(default_factory=RedundancyHints)
    
    # Signal quality
    signal_ratio: float = 0.0  # 0.0 to 1.0, higher = more signal
    noise_ratio: float = 0.0  # 0.0 to 1.0, higher = more noise
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class BlockContentAnalyzer:
    """
    Analyzes the content of a code block to determine signal vs noise.
    
    Uses cheap string-based heuristics - no ML, no LLM.
    Read-only: Never modifies the source.
    """
    
    # Patterns for classification
    COMMENT_PATTERN = re.compile(r'^\s*#(?!!).*$|^\s*//.*$')
    DOCSTRING_START = re.compile(r'^\s*["\']["\']["\']|^\s*"""')
    IMPORT_PATTERN = re.compile(r'^\s*(import\s+|from\s+\S+\s+import\s+)')
    ERROR_PATTERNS = [
        re.compile(r'\b(try|except|raise|finally)\b'),
        re.compile(r'\bexcept\s+\w+'),
        re.compile(r'\.raise_for_status\('),
    ]
    LOGGING_PATTERNS = [
        re.compile(r'\b(logger|logging|log)\.(debug|info|warning|error|critical|exception)\('),
        re.compile(r'\bprint\s*\('),
        re.compile(r'\bconsole\.(log|error|warn)\('),
    ]
    CONTROL_FLOW_PATTERN = re.compile(r'^\s*(if|elif|else|for|while|with|match|case)\b')
    FUNCTION_DEF_PATTERN = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)\s*\(')
    CLASS_DEF_PATTERN = re.compile(r'^\s*class\s+(\w+)')
    DECORATOR_PATTERN = re.compile(r'^\s*@\w+')
    IDENTIFIER_PATTERN = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')
    
    # Common non-identifiers to skip
    PYTHON_KEYWORDS = {
        'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 
        'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 
        'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 
        'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
        'True', 'False', 'None', 'self', 'cls'
    }
    
    COMMON_BUILTINS = {
        'str', 'int', 'float', 'bool', 'list', 'dict', 'set', 'tuple',
        'len', 'range', 'print', 'open', 'type', 'isinstance', 'hasattr',
        'getattr', 'setattr', 'super', 'property', 'staticmethod', 'classmethod',
        'Optional', 'Any', 'List', 'Dict', 'Set', 'Tuple', 'Union', 'Callable'
    }
    
    def analyze(self, content: str, block_id: str, file: str, symbol: str = "", 
                token_count: int = 0) -> IntraBlockDiagnostic:
        """
        Analyze a block's content for signal vs noise.
        
        Args:
            content: Raw code content of the block
            block_id: Unique identifier for the block
            file: Source file path
            symbol: Symbol name (function, class, etc.)
            token_count: Pre-computed token count
            
        Returns:
            IntraBlockDiagnostic with full analysis
        """
        lines = content.split('\n')
        total_lines = len(lines)
        
        # Estimate tokens if not provided
        if token_count == 0:
            token_count = self._estimate_tokens(content)
        
        # Analyze token composition
        breakdown = self._analyze_token_breakdown(lines)
        breakdown.total_lines = total_lines
        
        # Analyze identifier density
        identifiers = self._analyze_identifiers(content)
        
        # Analyze structural payload
        structural = self._analyze_structure(lines)
        
        # Analyze redundancy
        redundancy = self._analyze_redundancy(lines, content)
        
        # Compute signal/noise ratio
        signal_ratio, noise_ratio = self._compute_signal_noise(breakdown, redundancy)
        
        # Generate warnings
        warnings = self._generate_warnings(breakdown, identifiers, redundancy, signal_ratio)
        
        return IntraBlockDiagnostic(
            block_id=block_id,
            file=file,
            symbol=symbol,
            tokens=token_count,
            token_breakdown=breakdown,
            identifier_density=identifiers,
            structural_payload=structural,
            redundancy_hints=redundancy,
            signal_ratio=signal_ratio,
            noise_ratio=noise_ratio,
            warnings=warnings,
        )
    
    def _estimate_tokens(self, content: str) -> int:
        """Estimate token count using rough heuristic (4 chars per token)."""
        # Remove extra whitespace for better estimate
        cleaned = ' '.join(content.split())
        return max(1, len(cleaned) // 4)
    
    def _analyze_token_breakdown(self, lines: list[str]) -> TokenBreakdown:
        """Analyze the composition of tokens in the block."""
        if not lines:
            return TokenBreakdown()
        
        comment_lines = 0
        import_lines = 0
        docstring_lines = 0
        error_lines = 0
        logging_lines = 0
        control_flow_lines = 0
        signature_lines = 0
        code_lines = 0
        whitespace_lines = 0
        
        in_docstring = False
        
        for line in lines:
            stripped = line.strip()
            
            # Whitespace only
            if not stripped:
                whitespace_lines += 1
                continue
            
            # Docstring detection (multiline)
            if self.DOCSTRING_START.match(stripped):
                docstring_quote = '"""' if '"""' in stripped else "'''"
                # Check if docstring opens and closes on same line
                if stripped.count(docstring_quote) >= 2:
                    docstring_lines += 1
                    continue
                in_docstring = not in_docstring
                docstring_lines += 1
                continue
            
            if in_docstring:
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                docstring_lines += 1
                continue
            
            # Comments
            if self.COMMENT_PATTERN.match(stripped):
                comment_lines += 1
                continue
            
            # Imports
            if self.IMPORT_PATTERN.match(stripped):
                import_lines += 1
                continue
            
            # Function/method signatures
            if self.FUNCTION_DEF_PATTERN.match(stripped) or self.CLASS_DEF_PATTERN.match(stripped):
                signature_lines += 1
                continue
            
            # Decorators count as boilerplate/signature
            if self.DECORATOR_PATTERN.match(stripped):
                signature_lines += 1
                continue
            
            # Error handling
            if any(p.search(stripped) for p in self.ERROR_PATTERNS):
                error_lines += 1
                continue
            
            # Logging
            if any(p.search(stripped) for p in self.LOGGING_PATTERNS):
                logging_lines += 1
                continue
            
            # Control flow
            if self.CONTROL_FLOW_PATTERN.match(stripped):
                control_flow_lines += 1
                continue
            
            # Everything else is code logic
            code_lines += 1
        
        total = len(lines) if lines else 1
        non_whitespace = total - whitespace_lines
        
        # Calculate percentages based on non-whitespace lines
        base = non_whitespace if non_whitespace > 0 else 1
        
        return TokenBreakdown(
            code_logic_pct=round(safe_divide(code_lines, base, 0.0) * 100, 1),
            comments_pct=round(safe_divide(comment_lines, base, 0.0) * 100, 1),
            error_handling_pct=round(safe_divide(error_lines, base, 0.0) * 100, 1),
            logging_pct=round(safe_divide(logging_lines, base, 0.0) * 100, 1),
            imports_boiler_pct=round(safe_divide(import_lines, base, 0.0) * 100, 1),
            docstrings_pct=round(safe_divide(docstring_lines, base, 0.0) * 100, 1),
            signatures_pct=round(safe_divide(signature_lines, base, 0.0) * 100, 1),
            control_flow_pct=round(safe_divide(control_flow_lines, base, 0.0) * 100, 1),
            whitespace_pct=round(safe_divide(whitespace_lines, total, 0.0) * 100, 1),
            total_lines=total,
            comment_lines=comment_lines,
            import_lines=import_lines,
            docstring_lines=docstring_lines,
            error_lines=error_lines,
            logging_lines=logging_lines,
            control_flow_lines=control_flow_lines,
            signature_lines=signature_lines,
            code_lines=code_lines,
        )
    
    def _analyze_identifiers(self, content: str) -> IdentifierDensity:
        """Analyze identifier density and repetition."""
        # Find all identifiers
        all_identifiers = self.IDENTIFIER_PATTERN.findall(content)
        
        # Filter out keywords and common builtins
        meaningful = [
            ident for ident in all_identifiers 
            if ident not in self.PYTHON_KEYWORDS 
            and ident not in self.COMMON_BUILTINS
            and len(ident) > 1  # Skip single chars
        ]
        
        if not meaningful:
            return IdentifierDensity()
        
        # Count occurrences
        counts = Counter(meaningful)
        unique_count = len(counts)
        
        # Top 10 repeated (those appearing more than once)
        top_repeated = [
            (ident, count) for ident, count in counts.most_common(10)
            if count > 1
        ]
        
        # Density: unique identifiers per estimated tokens
        estimated_tokens = max(1, len(content.split()) // 2)  # rough token estimate
        density = safe_divide(unique_count, estimated_tokens, 0.0)
        
        return IdentifierDensity(
            total_unique=unique_count,
            top_repeated=top_repeated,
            density_ratio=round(density, 3),
        )
    
    def _analyze_structure(self, lines: list[str]) -> StructuralPayload:
        """Analyze structural elements in the block."""
        function_count = 0
        class_count = 0
        method_count = 0
        decorator_count = 0
        
        in_class = False
        current_indent = 0
        class_indent = 0
        max_depth = 0
        current_depth = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            # Calculate indent depth
            indent = len(line) - len(line.lstrip())
            indent_spaces = indent // 4 if indent > 0 else 0
            current_depth = indent_spaces
            max_depth = max(max_depth, current_depth)
            
            # Track class context
            if self.CLASS_DEF_PATTERN.match(stripped):
                class_count += 1
                in_class = True
                class_indent = indent
            
            # Function vs method
            if self.FUNCTION_DEF_PATTERN.match(stripped):
                if in_class and indent > class_indent:
                    method_count += 1
                else:
                    function_count += 1
                    if indent <= class_indent:
                        in_class = False
            
            # Decorators
            if self.DECORATOR_PATTERN.match(stripped):
                decorator_count += 1
        
        return StructuralPayload(
            function_count=function_count,
            class_count=class_count,
            method_count=method_count,
            decorator_count=decorator_count,
            nested_depth_max=max_depth,
        )
    
    def _analyze_redundancy(self, lines: list[str], content: str) -> RedundancyHints:
        """Detect redundancy patterns in the block."""
        patterns = []
        error_blocks = 0
        logging_calls = 0
        
        # Count try/except blocks
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('try:'):
                error_blocks += 1
            if any(p.search(stripped) for p in self.LOGGING_PATTERNS):
                logging_calls += 1
        
        # Check for repeated logging
        has_repeated_logging = logging_calls >= 3
        if has_repeated_logging:
            patterns.append("repeated logging")
        
        # Check for repeated error handling
        has_repeated_error = error_blocks >= 2
        if has_repeated_error:
            patterns.append("repeated error-handling blocks")
        
        # Check for repeated string patterns (potential copy-paste)
        line_set = [l.strip() for l in lines if l.strip() and len(l.strip()) > 20]
        line_counts = Counter(line_set)
        duplicates = [(l, c) for l, c in line_counts.items() if c > 1]
        if duplicates:
            patterns.append(f"{len(duplicates)} duplicate lines")
        
        # Boilerplate score based on composition
        boilerplate_score = 0.0
        total_classified = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            total_classified += 1
            # These are lower signal
            if (self.IMPORT_PATTERN.match(stripped) or 
                self.COMMENT_PATTERN.match(stripped) or
                any(p.search(stripped) for p in self.LOGGING_PATTERNS)):
                boilerplate_score += 1
        
        boilerplate_score = safe_divide(boilerplate_score, total_classified, 0.0)
        
        return RedundancyHints(
            repeated_patterns=patterns,
            error_handling_blocks=error_blocks,
            logging_calls=logging_calls,
            has_repeated_logging=has_repeated_logging,
            has_repeated_error_handling=has_repeated_error,
            boilerplate_score=round(boilerplate_score, 2),
        )
    
    def _compute_signal_noise(self, breakdown: TokenBreakdown, 
                               redundancy: RedundancyHints) -> tuple[float, float]:
        """
        Compute signal vs noise ratio.
        
        Signal: code_logic, control_flow, signatures (the actual implementation)
        Noise: excessive comments, logging, boilerplate, docstrings
        """
        # Signal components
        signal_pct = (
            breakdown.code_logic_pct + 
            breakdown.control_flow_pct + 
            breakdown.signatures_pct * 0.5  # Signatures are partial signal
        )
        
        # Noise components
        noise_pct = (
            breakdown.comments_pct * 0.5 +  # Comments aren't always noise
            breakdown.logging_pct + 
            breakdown.imports_boiler_pct +
            breakdown.docstrings_pct * 0.3 +  # Docstrings have some value
            redundancy.boilerplate_score * 20  # Boost for high boilerplate
        )
        
        total = signal_pct + noise_pct
        if total == 0:
            return 0.5, 0.5
        
        signal_ratio = min(1.0, signal_pct / 100)
        noise_ratio = min(1.0, noise_pct / 100)
        
        return round(signal_ratio, 2), round(noise_ratio, 2)
    
    def _generate_warnings(self, breakdown: TokenBreakdown,
                          identifiers: IdentifierDensity,
                          redundancy: RedundancyHints,
                          signal_ratio: float) -> list[str]:
        """Generate warnings based on analysis."""
        warnings = []
        
        # High noise ratio
        if signal_ratio < 0.3:
            warnings.append("High noise ratio detected")
        
        # Too many comments relative to code
        if breakdown.comments_pct > 40:
            warnings.append(f"Comment-heavy block ({breakdown.comments_pct:.0f}%)")
        
        # Too much logging
        if breakdown.logging_pct > 20:
            warnings.append(f"Logging-heavy block ({breakdown.logging_pct:.0f}%)")
        
        # Excessive error handling
        if breakdown.error_handling_pct > 30:
            warnings.append(f"Error-handling heavy ({breakdown.error_handling_pct:.0f}%)")
        
        # Redundancy issues
        if redundancy.has_repeated_logging:
            warnings.append("Repeated logging calls")
        if redundancy.has_repeated_error_handling:
            warnings.append("Multiple try/except blocks")
        
        # Low identifier density might indicate boilerplate
        if identifiers.total_unique < 5 and breakdown.total_lines > 20:
            warnings.append("Low identifier density (possible boilerplate)")
        
        return warnings


@dataclass(frozen=True)
class ContextBlockInfo:
    """Diagnostic info for a single context block."""
    
    block_id: str
    file: str
    start_line: int
    end_line: int
    tokens: int
    provenance: tuple[str, ...]
    position: int
    
    # Scores (may be None if not available)
    semantic_score: Optional[float] = None
    structural_score: Optional[float] = None
    final_score: Optional[float] = None


@dataclass
class ContextDiagnosticResult:
    """Complete context diagnostic result."""
    
    query_id: str | int | None
    run_id: str | None
    total_blocks: int
    total_tokens: int
    token_budget: int
    used_budget_pct: float
    
    # Block details
    blocks: list[ContextBlockInfo] = field(default_factory=list)
    
    # Derived signals
    top_k_token_concentration: float = 0.0  # % tokens in top 5 blocks
    structural_dominance_pct: float = 0.0
    semantic_dominance_pct: float = 0.0
    
    # Redundancy
    redundant_blocks: list[dict[str, Any]] = field(default_factory=list)
    
    # Budget analysis
    dropped_due_to_budget: int = 0
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class ContextDiagnostics:
    """
    Context assembly diagnostics.
    
    Analyzes context artifacts to understand:
    - What blocks were included
    - Why they were selected
    - Token budget utilization
    - Redundancy and noise
    
    Read-only: Never modifies source data.
    """
    
    def __init__(self, artifacts_path: Path, indexes_path: Optional[Path] = None):
        """
        Initialize context diagnostics.
        
        Args:
            artifacts_path: Path to artifacts directory
            indexes_path: Path to indexes directory (for symbol lookup)
        """
        self.artifacts_path = Path(artifacts_path)
        self.indexes_path = Path(indexes_path) if indexes_path else None
        self.runs_path = self.artifacts_path / "runs"
        
        # Load symbol metadata if available
        self._symbols_map: dict[str, dict] = {}
        if self.indexes_path:
            self._load_symbols()
    
    def _load_symbols(self) -> None:
        """Load symbol metadata for block enrichment."""
        symbols_file = self.indexes_path / "symbols.json"
        if not symbols_file.exists():
            return
        
        try:
            with open(symbols_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for symbol in data.get("symbols", []):
                symbol_id = symbol.get("id", "")
                if symbol_id:
                    self._symbols_map[symbol_id] = symbol
        except (json.JSONDecodeError, IOError):
            pass
    
    def analyze_run(self, run_id: str) -> Optional[ContextDiagnosticResult]:
        """
        Analyze context assembly for a specific run.
        
        Args:
            run_id: Run ID to analyze
        
        Returns:
            ContextDiagnosticResult or None if run not found
        """
        telemetry_file = self.runs_path / run_id / "telemetry.json"
        if not telemetry_file.exists():
            return None
        
        try:
            with open(telemetry_file, "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
        
        # Extract context phase data
        context_phase = telemetry.get("phases", {}).get("CONTEXT", {})
        
        total_blocks = context_phase.get("blocks", 0)
        total_tokens = context_phase.get("tokens", 0)
        token_budget = context_phase.get("token_budget", 4000)
        
        # Build result
        result = ContextDiagnosticResult(
            query_id=None,
            run_id=run_id,
            total_blocks=total_blocks,
            total_tokens=total_tokens,
            token_budget=token_budget,
            used_budget_pct=safe_divide(total_tokens, token_budget, 0.0) * 100,
        )
        
        # Add warnings based on analysis
        if result.used_budget_pct > 95:
            result.warnings.append(f"Near budget limit: {result.used_budget_pct:.1f}% used")
        
        if total_blocks == 0:
            result.warnings.append("No context blocks - empty context generated")
        
        return result
    
    def analyze_with_provenance(
        self, 
        run_id: str,
        context_data: Optional[dict] = None
    ) -> Optional[ContextDiagnosticResult]:
        """
        Analyze context with full provenance data.
        
        This method expects context data with block-level details
        from the context pipeline's provenance output.
        
        Args:
            run_id: Run ID
            context_data: Context data with provenance (from context artifact)
        
        Returns:
            ContextDiagnosticResult with full block analysis
        """
        # Start with basic analysis
        result = self.analyze_run(run_id)
        if result is None:
            return None
        
        if not context_data:
            return result
        
        # Parse provenance blocks
        blocks_data = context_data.get("provenance", {}).get("blocks", [])
        blocks = []
        
        for i, block_data in enumerate(blocks_data):
            block_id = block_data.get("block_id", f"block_{i}")
            
            block_info = ContextBlockInfo(
                block_id=block_id,
                file=block_data.get("file", "unknown"),
                start_line=block_data.get("start_line", 0),
                end_line=block_data.get("end_line", 0),
                tokens=block_data.get("tokens", 0),
                provenance=tuple(block_data.get("provenance", [])),
                position=i,
                semantic_score=block_data.get("semantic_score"),
                structural_score=block_data.get("structural_score"),
                final_score=block_data.get("final_score"),
            )
            blocks.append(block_info)
        
        result.blocks = blocks
        
        # Compute derived signals
        if blocks:
            self._compute_token_concentration(result)
            self._compute_dominance_ratios(result)
            self._detect_redundancy(result)
        
        return result
    
    def _compute_token_concentration(self, result: ContextDiagnosticResult) -> None:
        """Compute token concentration in top K blocks."""
        if not result.blocks or result.total_tokens == 0:
            return
        
        # Sort by tokens descending
        sorted_blocks = sorted(result.blocks, key=lambda b: b.tokens, reverse=True)
        
        # Top 5 blocks
        top_k = 5
        top_tokens = sum(b.tokens for b in sorted_blocks[:top_k])
        result.top_k_token_concentration = safe_divide(top_tokens, result.total_tokens, 0.0) * 100
        
        # Warning if concentration is very high
        if result.top_k_token_concentration > 80 and len(result.blocks) > 10:
            result.warnings.append(
                f"High token concentration: top {top_k} blocks use {result.top_k_token_concentration:.0f}% of tokens"
            )
    
    def _compute_dominance_ratios(self, result: ContextDiagnosticResult) -> None:
        """Compute structural vs semantic dominance."""
        structural_scores = []
        semantic_scores = []
        
        for block in result.blocks:
            if block.structural_score is not None:
                structural_scores.append(block.structural_score)
            if block.semantic_score is not None:
                semantic_scores.append(block.semantic_score)
        
        if not structural_scores and not semantic_scores:
            return
        
        total_structural = sum(structural_scores) if structural_scores else 0
        total_semantic = sum(semantic_scores) if semantic_scores else 0
        total = total_structural + total_semantic
        
        if total > 0:
            result.structural_dominance_pct = safe_divide(total_structural, total, 0.0) * 100
            result.semantic_dominance_pct = safe_divide(total_semantic, total, 0.0) * 100
    
    def _detect_redundancy(self, result: ContextDiagnosticResult) -> None:
        """Detect redundant blocks from same file."""
        # Group blocks by file
        file_groups: dict[str, list[ContextBlockInfo]] = {}
        for block in result.blocks:
            if block.file not in file_groups:
                file_groups[block.file] = []
            file_groups[block.file].append(block)
        
        # Check for overlapping or adjacent blocks from same file
        for file, blocks in file_groups.items():
            if len(blocks) >= 3:
                # 3+ blocks from same file is potential redundancy
                result.redundant_blocks.append({
                    "file": file,
                    "block_count": len(blocks),
                    "total_tokens": sum(b.tokens for b in blocks),
                    "lines_covered": (
                        min(b.start_line for b in blocks),
                        max(b.end_line for b in blocks)
                    ),
                })
                result.warnings.append(
                    f"Potential redundancy: {len(blocks)} blocks from {file}"
                )
    
    def to_diagnostic_result(self, ctx_result: ContextDiagnosticResult) -> DiagnosticResult:
        """Convert to standard DiagnosticResult for formatting."""
        summary = {
            "total_blocks": ctx_result.total_blocks,
            "total_tokens": ctx_result.total_tokens,
            "token_budget": ctx_result.token_budget,
            "used_budget_pct": f"{ctx_result.used_budget_pct:.1f}%",
            "top_5_token_concentration": f"{ctx_result.top_k_token_concentration:.1f}%",
            "structural_dominance": f"{ctx_result.structural_dominance_pct:.1f}%",
            "semantic_dominance": f"{ctx_result.semantic_dominance_pct:.1f}%",
        }
        
        details = []
        for block in ctx_result.blocks[:10]:  # Top 10 for display
            details.append({
                "block_id": block.block_id,
                "file": block.file.split("\\")[-1] if "\\" in block.file else block.file.split("/")[-1],
                "lines": f"{block.start_line}-{block.end_line}",
                "tokens": block.tokens,
                "provenance": ", ".join(block.provenance) if block.provenance else "-",
            })
        
        return DiagnosticResult(
            phase="context",
            query_id=ctx_result.query_id,
            run_id=ctx_result.run_id,
            summary=summary,
            details=details,
            warnings=ctx_result.warnings,
        )
    
    def list_runs(self) -> list[str]:
        """List all available run IDs."""
        if not self.runs_path.exists():
            return []
        return [d.name for d in self.runs_path.iterdir() if d.is_dir()]
    
    # =========================================================================
    # INTRA-BLOCK ANALYSIS (STEP 2)
    # =========================================================================
    
    def analyze_block_content(
        self,
        content: str,
        block_id: str,
        file: str,
        symbol: str = "",
        token_count: int = 0
    ) -> IntraBlockDiagnostic:
        """
        Analyze the content of a single block for signal vs noise.
        
        Args:
            content: Raw code content of the block
            block_id: Unique identifier for the block
            file: Source file path
            symbol: Symbol name (function, class, etc.)
            token_count: Pre-computed token count
            
        Returns:
            IntraBlockDiagnostic with full analysis
        """
        analyzer = BlockContentAnalyzer()
        return analyzer.analyze(content, block_id, file, symbol, token_count)
    
    def analyze_blocks_from_source(
        self,
        blocks: list[ContextBlockInfo],
        source_path: Path
    ) -> list[IntraBlockDiagnostic]:
        """
        Analyze all blocks by reading their content from source files.
        
        Args:
            blocks: List of ContextBlockInfo with file/line info
            source_path: Root path to source files
            
        Returns:
            List of IntraBlockDiagnostic for each block
        """
        analyzer = BlockContentAnalyzer()
        results = []
        
        # Cache file contents to avoid repeated reads
        file_cache: dict[str, list[str]] = {}
        
        for block in blocks:
            # Resolve file path
            file_path = source_path / block.file if not Path(block.file).is_absolute() else Path(block.file)
            
            # Get file content from cache or read
            if str(file_path) not in file_cache:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_cache[str(file_path)] = f.readlines()
                except (IOError, OSError):
                    # Skip blocks we can't read
                    continue
            
            lines = file_cache.get(str(file_path), [])
            if not lines:
                continue
            
            # Extract block content (1-indexed to 0-indexed)
            start_idx = max(0, block.start_line - 1)
            end_idx = min(len(lines), block.end_line)
            block_content = "".join(lines[start_idx:end_idx])
            
            # Analyze the block
            diagnostic = analyzer.analyze(
                content=block_content,
                block_id=block.block_id,
                file=block.file,
                symbol=block.block_id,  # Use block_id as symbol if not available
                token_count=block.tokens
            )
            results.append(diagnostic)
        
        return results


# =============================================================================
# INTRA-BLOCK DIAGNOSTIC FORMATTER (STEP 3)
# =============================================================================

def format_intra_block_diagnostic(
    diagnostic: IntraBlockDiagnostic,
    block_position: int = 0
) -> str:
    """
    Format an intra-block diagnostic for display.
    
    Output format matches the requested format:
    
    [CONTEXT BLOCK N]
    File        : filename.py
    Symbol      : ClassName.method_name
    Tokens      : NNN
    Token Breakdown:
      Code logic        : XX%
      Comments          : XX%
      ...
    Signal Indicators:
      Functions         : N
      Key identifiers   : id1, id2, id3
      Redundancy flags  : flag description
    ⚠ Warning messages
    
    Args:
        diagnostic: IntraBlockDiagnostic to format
        block_position: Block position in context (1-indexed for display)
        
    Returns:
        Formatted string representation
    """
    lines = []
    
    # Header
    lines.append(f"[CONTEXT BLOCK {block_position}]")
    
    # Basic info
    filename = Path(diagnostic.file).name if diagnostic.file else "unknown"
    lines.append(f"File        : {filename}")
    lines.append(f"Symbol      : {diagnostic.symbol}")
    lines.append(f"Tokens      : {diagnostic.tokens}")
    
    # Token breakdown
    tb = diagnostic.token_breakdown
    lines.append("Token Breakdown:")
    lines.append(f"  Code logic        : {tb.code_logic_pct:.0f}%")
    lines.append(f"  Comments          : {tb.comments_pct:.0f}%")
    lines.append(f"  Error handling    : {tb.error_handling_pct:.0f}%")
    lines.append(f"  Logging           : {tb.logging_pct:.0f}%")
    lines.append(f"  Imports/boiler    : {tb.imports_boiler_pct:.0f}%")
    lines.append(f"  Docstrings        : {tb.docstrings_pct:.0f}%")
    lines.append(f"  Signatures        : {tb.signatures_pct:.0f}%")
    lines.append(f"  Control flow      : {tb.control_flow_pct:.0f}%")
    
    # Signal indicators
    sp = diagnostic.structural_payload
    id_info = diagnostic.identifier_density
    rh = diagnostic.redundancy_hints
    
    lines.append("Signal Indicators:")
    
    # Functions/Classes/Methods
    struct_parts = []
    if sp.function_count > 0:
        struct_parts.append(f"Functions: {sp.function_count}")
    if sp.class_count > 0:
        struct_parts.append(f"Classes: {sp.class_count}")
    if sp.method_count > 0:
        struct_parts.append(f"Methods: {sp.method_count}")
    if struct_parts:
        lines.append(f"  {', '.join(struct_parts)}")
    
    # Key identifiers
    if id_info.top_repeated:
        key_ids = [ident for ident, _ in id_info.top_repeated[:5]]
        lines.append(f"  Key identifiers   : {', '.join(key_ids)}")
    elif id_info.total_unique > 0:
        lines.append(f"  Unique identifiers: {id_info.total_unique}")
    
    # Redundancy flags
    if rh.repeated_patterns:
        lines.append(f"  Redundancy flags  : {', '.join(rh.repeated_patterns)}")
    
    # Warnings
    for warning in diagnostic.warnings:
        lines.append(f"! {warning}")
    
    return "\n".join(lines)


def format_all_blocks(diagnostics: list[IntraBlockDiagnostic]) -> str:
    """
    Format all block diagnostics as a complete report.
    
    Args:
        diagnostics: List of IntraBlockDiagnostic objects
        
    Returns:
        Complete formatted report string
    """
    parts = []
    
    # Summary header
    parts.append("=" * 60)
    parts.append("INTRA-BLOCK CONTEXT DIAGNOSTICS")
    parts.append("=" * 60)
    parts.append("")
    
    # Aggregate stats
    total_tokens = sum(d.tokens for d in diagnostics)
    total_signal = sum(d.signal_ratio * d.tokens for d in diagnostics)
    total_noise = sum(d.noise_ratio * d.tokens for d in diagnostics)
    
    avg_signal = safe_divide(total_signal, total_tokens, 0.5)
    avg_noise = safe_divide(total_noise, total_tokens, 0.5)
    
    parts.append(f"Total Blocks: {len(diagnostics)}")
    parts.append(f"Total Tokens: {total_tokens}")
    parts.append(f"Avg Signal Ratio: {avg_signal:.1%}")
    parts.append(f"Avg Noise Ratio: {avg_noise:.1%}")
    parts.append("")
    
    # High-noise blocks warning
    high_noise = [d for d in diagnostics if d.noise_ratio > 0.4]
    if high_noise:
        parts.append(f"! {len(high_noise)} blocks with high noise ratio (>40%)")
        parts.append("")
    
    parts.append("-" * 60)
    parts.append("")
    
    # Individual blocks
    for i, diag in enumerate(diagnostics, 1):
        parts.append(format_intra_block_diagnostic(diag, i))
        parts.append("")
        parts.append("-" * 40)
        parts.append("")
    
    return "\n".join(parts)


# =============================================================================
# DEMO / TEST FUNCTION
# =============================================================================

def demo_analyze_sample_block() -> str:
    """
    Demo function: Analyze a sample code block and return formatted diagnostic.
    
    This demonstrates the intra-block analysis on a typical problematic block.
    """
    sample_code = '''
def query_optimizer_optimize(self, query: str, rules: list[Rule]) -> OptimizedQuery:
    """
    Optimize the given query using predefined rules.
    
    This method applies a series of optimization rules to transform
    the input query into a more efficient form.
    
    Args:
        query: The raw query string to optimize
        rules: List of Rule objects to apply
        
    Returns:
        OptimizedQuery object with the optimized query
    """
    logger.info(f"Starting optimization for query: {query[:50]}...")
    
    # Validate inputs
    if not query:
        logger.error("Empty query provided")
        raise ValueError("Query cannot be empty")
    
    if not rules:
        logger.warning("No rules provided, returning original query")
        return OptimizedQuery(query=query, applied_rules=[])
    
    try:
        # Apply each rule in sequence
        optimized = query
        applied = []
        
        for rule in rules:
            logger.debug(f"Applying rule: {rule.name}")
            try:
                result = rule.apply(optimized)
                if result != optimized:
                    logger.info(f"Rule {rule.name} modified query")
                    applied.append(rule.name)
                    optimized = result
            except Exception as e:
                logger.error(f"Rule {rule.name} failed: {e}")
                continue
        
        logger.info(f"Optimization complete. Applied {len(applied)} rules.")
        return OptimizedQuery(query=optimized, applied_rules=applied)
        
    except Exception as e:
        logger.exception("Optimization failed unexpectedly")
        raise OptimizationError(f"Failed to optimize query: {e}") from e
'''
    
    analyzer = BlockContentAnalyzer()
    diagnostic = analyzer.analyze(
        content=sample_code,
        block_id="block_3",
        file="query_optimizer.py",
        symbol="QueryOptimizer.optimize",
        token_count=820  # Approximate
    )
    
    return format_intra_block_diagnostic(diagnostic, block_position=3)

