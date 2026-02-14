"""
Unit tests for Level-1 Alignment Observability Layer.

Tests verify:
- Determinism (same input → same output)
- Zero side effects when disabled
- Correct signal computation
- Risk indicator derivation
- AlignmentReport immutability
- JSON serialization
"""

import pytest
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

# Test imports
from homllm.alignment import (
    AlignmentReport,
    SemanticAlignment,
    StructuralAlignment,
    GroundingAlignment,
    RiskIndicators,
    AlignmentAnalyzer,
    create_alignment_analyzer,
)
from homllm.alignment.semantic import compute_semantic_alignment, _cosine_similarity
from homllm.alignment.structural import compute_structural_alignment
from homllm.alignment.grounding import compute_grounding_alignment


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_embedder():
    """Create a mock embedder for testing."""
    embedder = MagicMock()
    
    # Return consistent vectors for determinism testing
    def embed_query(query):
        vector = MagicMock()
        vector.values = (0.5, 0.5, 0.5, 0.5)
        return vector
    
    def embed_code(code):
        # Return different vectors based on code content hash
        # to simulate different embeddings for different blocks
        code_hash = hash(code) % 10
        if code_hash < 3:
            vector = MagicMock()
            vector.values = (0.6, 0.4, 0.5, 0.5)  # Similar to query
        elif code_hash < 6:
            vector = MagicMock()
            vector.values = (0.3, 0.7, 0.2, 0.8)  # Less similar
        else:
            vector = MagicMock()
            vector.values = (0.1, 0.9, 0.1, 0.9)  # Even less similar
        return vector
    
    embedder.embed_query = embed_query
    embedder.embed_code = embed_code
    return embedder


@pytest.fixture
def mock_context_artifact():
    """Create a mock context artifact."""
    artifact = MagicMock()
    
    # Create mock blocks
    block1 = MagicMock()
    block1.file = "file1.py"
    block1.content = "def foo(): pass"
    
    block2 = MagicMock()
    block2.file = "file2.py"
    block2.content = "def bar(): return 1"
    
    block3 = MagicMock()
    block3.file = "file1.py"  # Same file as block1
    block3.content = "class MyClass: pass"
    
    artifact.blocks = (block1, block2, block3)
    return artifact


@pytest.fixture
def mock_reasoning_contract():
    """Create a mock reasoning contract."""
    from homllm.intelligence.reasoning_contracts.interfaces import (
        ReasoningContract, ReasoningStep, ContractSeverity, Constraint
    )
    
    return ReasoningContract(
        required_steps=(
            ReasoningStep.ENUMERATION_REQUIRED,
            ReasoningStep.TRACE_REQUIRED,
        ),
        constraints=(
            Constraint(step=ReasoningStep.ENUMERATION_REQUIRED, reason="Test", evidence_count=2),
        ),
        severity=ContractSeverity.REQUIRED,
    )


@pytest.fixture
def mock_readability_result():
    """Create a mock readability result."""
    from homllm.intelligence.assertion_readability.interfaces import ReadabilityResult
    
    return ReadabilityResult(
        total_blocks=5,
        readable_count=3,
        suppressed_count=2,
        protected_but_readable_count=1,
        entries=(),
    )


# =============================================================================
# Data Structure Tests
# =============================================================================

class TestAlignmentReportImmutability:
    """Tests for frozen dataclass behavior."""
    
    def test_alignment_report_is_frozen(self):
        """AlignmentReport should be immutable."""
        report = AlignmentReport.empty()
        with pytest.raises(FrozenInstanceError):
            report.semantic_alignment = SemanticAlignment.empty()
    
    def test_semantic_alignment_is_frozen(self):
        """SemanticAlignment should be immutable."""
        alignment = SemanticAlignment.empty()
        with pytest.raises(FrozenInstanceError):
            alignment.mean_similarity = 0.5
    
    def test_structural_alignment_is_frozen(self):
        """StructuralAlignment should be immutable."""
        alignment = StructuralAlignment.empty()
        with pytest.raises(FrozenInstanceError):
            alignment.readable_block_count = 10
    
    def test_grounding_alignment_is_frozen(self):
        """GroundingAlignment should be immutable."""
        alignment = GroundingAlignment.empty()
        with pytest.raises(FrozenInstanceError):
            alignment.estimated_claim_count = 5
    
    def test_risk_indicators_is_frozen(self):
        """RiskIndicators should be immutable."""
        indicators = RiskIndicators.empty()
        with pytest.raises(FrozenInstanceError):
            indicators.semantic_drift = "high"


class TestAlignmentReportSerialization:
    """Tests for JSON serialization."""
    
    def test_empty_report_to_dict(self):
        """Empty report should serialize correctly."""
        report = AlignmentReport.empty()
        result = report.to_dict()
        
        assert "semantic_alignment" in result
        assert "structural_alignment" in result
        assert "grounding_alignment" in result
        assert "risk_indicators" in result
    
    def test_semantic_alignment_to_dict(self):
        """SemanticAlignment should serialize with rounded values."""
        alignment = SemanticAlignment(
            mean_similarity=0.123456789,
            min_similarity=0.1,
            max_similarity=0.9,
            similarity_variance=0.000001234,
            outlier_block_count=2,
            block_similarities=(0.1, 0.5, 0.9),
        )
        result = alignment.to_dict()
        
        # Check rounding
        assert result["mean_similarity"] == 0.1235  # 4 decimals
        assert result["similarity_variance"] == 0.000001  # 6 decimals
        assert result["block_count"] == 3
    
    def test_full_report_is_json_serializable(self):
        """Full report should be JSON-serializable."""
        import json
        
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.5,
                min_similarity=0.1,
                max_similarity=0.9,
                similarity_variance=0.01,
                outlier_block_count=1,
                block_similarities=(0.1, 0.5, 0.9),
            ),
            structural_alignment=StructuralAlignment(
                expected_reasoning_steps=2,
                readable_block_count=3,
                distinct_component_count=2,
                structural_support_matrix={"step1": True, "step2": False},
            ),
            grounding_alignment=GroundingAlignment(
                estimated_claim_count=5,
                grounding_reference_capacity=10,
                grounding_pressure_ratio=0.5,
            ),
            risk_indicators=RiskIndicators(
                semantic_drift="low",
                structural_gap="medium",
                grounding_pressure="high",
            ),
        )
        
        # Should not raise
        result = json.dumps(report.to_dict())
        assert isinstance(result, str)


# =============================================================================
# Computation Tests
# =============================================================================

class TestCosineSimlarity:
    """Tests for cosine similarity computation."""
    
    def test_identical_vectors(self):
        """Identical vectors should have similarity 1."""
        vec = (0.5, 0.5, 0.5, 0.5)
        result = _cosine_similarity(vec, vec)
        assert abs(result - 1.0) < 0.0001
    
    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1."""
        vec1 = (1.0, 0.0)
        vec2 = (-1.0, 0.0)
        result = _cosine_similarity(vec1, vec2)
        assert abs(result - (-1.0)) < 0.0001
    
    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity 0."""
        vec1 = (1.0, 0.0)
        vec2 = (0.0, 1.0)
        result = _cosine_similarity(vec1, vec2)
        assert abs(result) < 0.0001
    
    def test_empty_vectors(self):
        """Empty vectors should return 0."""
        result = _cosine_similarity((), ())
        assert result == 0.0
    
    def test_zero_vectors(self):
        """Zero vectors should return 0."""
        result = _cosine_similarity((0.0, 0.0), (1.0, 1.0))
        assert result == 0.0


class TestSemanticAlignment:
    """Tests for semantic alignment computation."""
    
    def test_empty_context_returns_empty(self, mock_embedder):
        """Empty context should return empty alignment."""
        artifact = MagicMock()
        artifact.blocks = ()
        
        result = compute_semantic_alignment("query", artifact, mock_embedder)
        
        assert result.mean_similarity == 0.0
        assert result.block_similarities == ()
    
    def test_computes_statistics(self, mock_embedder, mock_context_artifact):
        """Should compute mean, min, max, variance."""
        result = compute_semantic_alignment(
            "test query", mock_context_artifact, mock_embedder
        )
        
        assert result.mean_similarity != 0.0
        assert result.min_similarity <= result.mean_similarity <= result.max_similarity
        assert result.similarity_variance >= 0.0
        assert len(result.block_similarities) == 3


class TestStructuralAlignment:
    """Tests for structural alignment computation."""
    
    def test_counts_expected_steps(self, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Should count expected reasoning steps."""
        result = compute_structural_alignment(
            mock_context_artifact, mock_reasoning_contract, mock_readability_result
        )
        
        assert result.expected_reasoning_steps == 2
    
    def test_counts_distinct_components(self, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Should count distinct file components."""
        result = compute_structural_alignment(
            mock_context_artifact, mock_reasoning_contract, mock_readability_result
        )
        
        # block1 and block3 are in file1.py, block2 is in file2.py
        assert result.distinct_component_count == 2
    
    def test_builds_support_matrix(self, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Should build structural support matrix."""
        result = compute_structural_alignment(
            mock_context_artifact, mock_reasoning_contract, mock_readability_result
        )
        
        assert "enumeration_required" in result.structural_support_matrix
        assert "trace_required" in result.structural_support_matrix
    
    def test_handles_no_contract(self, mock_context_artifact, mock_readability_result):
        """Should handle None reasoning contract."""
        result = compute_structural_alignment(
            mock_context_artifact, None, mock_readability_result
        )
        
        assert result.expected_reasoning_steps == 0
        assert result.structural_support_matrix == {}


class TestGroundingAlignment:
    """Tests for grounding alignment computation."""
    
    def test_estimates_claims(self, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Should estimate claim count from contract."""
        result = compute_grounding_alignment(
            mock_context_artifact, mock_reasoning_contract, mock_readability_result
        )
        
        # Base claims (2) + enumeration (3) + trace (5) = 10
        assert result.estimated_claim_count == 10
    
    def test_computes_capacity(self, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Should compute grounding capacity."""
        result = compute_grounding_alignment(
            mock_context_artifact, mock_reasoning_contract, mock_readability_result
        )
        
        # readable_count (3) * 2 + distinct_components (2) * 1 = 8
        assert result.grounding_reference_capacity == 8
    
    def test_computes_pressure_ratio(self, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Should compute pressure ratio."""
        result = compute_grounding_alignment(
            mock_context_artifact, mock_reasoning_contract, mock_readability_result
        )
        
        # claims (10) / capacity (8) = 1.25
        assert abs(result.grounding_pressure_ratio - 1.25) < 0.01


# =============================================================================
# Analyzer Tests
# =============================================================================

class TestAlignmentAnalyzer:
    """Tests for main analyzer."""
    
    def test_disabled_returns_none(self, mock_embedder, mock_context_artifact):
        """Disabled analyzer should return None immediately."""
        analyzer = AlignmentAnalyzer(embedder=mock_embedder, enabled=False)
        result = analyzer.analyze(
            query="test",
            context_artifact=mock_context_artifact,
        )
        
        assert result is None
    
    def test_enabled_returns_report(self, mock_embedder, mock_context_artifact):
        """Enabled analyzer should return AlignmentReport."""
        analyzer = AlignmentAnalyzer(embedder=mock_embedder, enabled=True)
        result = analyzer.analyze(
            query="test",
            context_artifact=mock_context_artifact,
        )
        
        assert result is not None
        assert isinstance(result, AlignmentReport)
    
    def test_determinism(self, mock_embedder, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Same inputs should produce identical outputs."""
        analyzer = AlignmentAnalyzer(embedder=mock_embedder, enabled=True)
        
        result1 = analyzer.analyze(
            query="test query",
            context_artifact=mock_context_artifact,
            reasoning_contract=mock_reasoning_contract,
            readability_result=mock_readability_result,
        )
        
        result2 = analyzer.analyze(
            query="test query",
            context_artifact=mock_context_artifact,
            reasoning_contract=mock_reasoning_contract,
            readability_result=mock_readability_result,
        )
        
        assert result1.to_dict() == result2.to_dict()
    
    def test_factory_function(self, mock_embedder):
        """Factory function should create configured analyzer."""
        analyzer = create_alignment_analyzer(mock_embedder, enabled=True)
        
        assert isinstance(analyzer, AlignmentAnalyzer)
        assert analyzer.enabled is True
    
    def test_factory_disabled_by_default(self, mock_embedder):
        """Factory should create disabled analyzer by default."""
        analyzer = create_alignment_analyzer(mock_embedder)
        
        assert analyzer.enabled is False


class TestRiskIndicatorDerivation:
    """Tests for risk indicator derivation logic."""
    
    def test_high_semantic_drift(self, mock_embedder, mock_context_artifact):
        """Low similarity should produce high semantic drift."""
        # Create embedder that returns very different vectors
        embedder = MagicMock()
        embedder.embed_query = lambda q: MagicMock(values=(1.0, 0.0, 0.0, 0.0))
        embedder.embed_code = lambda c: MagicMock(values=(0.0, 1.0, 0.0, 0.0))  # Orthogonal
        
        analyzer = AlignmentAnalyzer(embedder=embedder, enabled=True)
        result = analyzer.analyze("test", mock_context_artifact)
        
        # Orthogonal vectors have 0 similarity, which is < 0.3, so high drift
        assert result.risk_indicators.semantic_drift == "high"
    
    def test_low_grounding_pressure(self, mock_embedder, mock_context_artifact, mock_readability_result):
        """Low pressure ratio should produce low grounding pressure."""
        # With no contract, claims = 2 (base only)
        # With readability result having readable_count=3 and 2 components
        # capacity = 3*2 + 2*1 = 8, pressure = 2/8 = 0.25 < 1.0 → low
        
        analyzer = AlignmentAnalyzer(embedder=mock_embedder, enabled=True)
        result = analyzer.analyze(
            "test",
            mock_context_artifact,
            reasoning_contract=None,
            readability_result=mock_readability_result,
        )
        
        assert result.risk_indicators.grounding_pressure == "low"


# =============================================================================
# Zero Side Effects Tests
# =============================================================================

class TestZeroSideEffects:
    """Tests that alignment layer has no side effects."""
    
    def test_does_not_modify_context(self, mock_embedder, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Analyzer should not modify context artifact."""
        original_blocks = mock_context_artifact.blocks
        
        analyzer = AlignmentAnalyzer(embedder=mock_embedder, enabled=True)
        analyzer.analyze(
            "test",
            mock_context_artifact,
            mock_reasoning_contract,
            mock_readability_result,
        )
        
        assert mock_context_artifact.blocks is original_blocks
    
    def test_does_not_modify_contract(self, mock_embedder, mock_context_artifact, mock_reasoning_contract, mock_readability_result):
        """Analyzer should not modify reasoning contract."""
        original_steps = mock_reasoning_contract.required_steps
        
        analyzer = AlignmentAnalyzer(embedder=mock_embedder, enabled=True)
        analyzer.analyze(
            "test",
            mock_context_artifact,
            mock_reasoning_contract,
            mock_readability_result,
        )
        
        assert mock_reasoning_contract.required_steps is original_steps
    
    def test_no_embedder_calls_when_disabled(self, mock_context_artifact):
        """Disabled analyzer should not call embedder at all."""
        embedder = MagicMock()
        
        analyzer = AlignmentAnalyzer(embedder=embedder, enabled=False)
        analyzer.analyze("test", mock_context_artifact)
        
        embedder.embed_query.assert_not_called()
        embedder.embed_code.assert_not_called()
