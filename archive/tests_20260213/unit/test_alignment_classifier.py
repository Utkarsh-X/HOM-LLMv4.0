"""
Unit tests for Level-2 Alignment Failure Classification.

Tests verify:
- Each failure type trigger
- Multi-failure scenarios
- LOW_RISK case
- Determinism (same input → same output)
- JSON serialization
- Immutability (frozen dataclass)
- Zero side effects
"""

import pytest
import json
from dataclasses import FrozenInstanceError

from homllm.alignment import (
    FailureType,
    AlignmentFailureReport,
    AlignmentClassifier,
    create_alignment_classifier,
    AlignmentReport,
    SemanticAlignment,
    StructuralAlignment,
    GroundingAlignment,
    RiskIndicators,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def healthy_alignment_report():
    """Create a healthy alignment report with no failure triggers."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.8,  # > 0.5 threshold
            min_similarity=0.6,
            max_similarity=0.95,
            similarity_variance=0.01,  # < 0.05 threshold
            outlier_block_count=0,  # No outliers
            block_similarities=(0.75, 0.8, 0.85),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=2,
            readable_block_count=5,  # > expected steps (no structural gap)
            distinct_component_count=3,
            structural_support_matrix={"step1": True, "step2": True},  # All supported
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=5,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=0.5,  # < 1.0 threshold
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="low",
            structural_gap="low",
            grounding_pressure="low",
        ),
    )


@pytest.fixture
def semantic_drift_report():
    """Create report with semantic drift trigger."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.3,  # < 0.5 threshold → SEMANTIC_DRIFT
            min_similarity=0.1,
            max_similarity=0.5,
            similarity_variance=0.02,
            outlier_block_count=0,
            block_similarities=(0.2, 0.3, 0.4),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=2,
            readable_block_count=5,
            distinct_component_count=3,
            structural_support_matrix={"step1": True, "step2": True},
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=5,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=0.5,
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="high",
            structural_gap="low",
            grounding_pressure="low",
        ),
    )


@pytest.fixture
def structural_gap_report():
    """Create report with structural gap trigger."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.8,
            min_similarity=0.6,
            max_similarity=0.95,
            similarity_variance=0.01,
            outlier_block_count=0,
            block_similarities=(0.75, 0.8, 0.85),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=10,  # > readable_block_count → STRUCTURAL_GAP
            readable_block_count=3,
            distinct_component_count=2,
            structural_support_matrix={"step1": True, "step2": True},
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=5,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=0.5,
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="low",
            structural_gap="high",
            grounding_pressure="low",
        ),
    )


@pytest.fixture
def grounding_pressure_report():
    """Create report with grounding pressure trigger."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.8,
            min_similarity=0.6,
            max_similarity=0.95,
            similarity_variance=0.01,
            outlier_block_count=0,
            block_similarities=(0.75, 0.8, 0.85),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=2,
            readable_block_count=5,
            distinct_component_count=3,
            structural_support_matrix={"step1": True, "step2": True},
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=20,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=2.0,  # > 1.0 threshold → GROUNDING_PRESSURE
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="low",
            structural_gap="low",
            grounding_pressure="high",
        ),
    )


@pytest.fixture
def overconstrained_report():
    """Create report with overconstrained context trigger."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.8,
            min_similarity=0.6,
            max_similarity=0.95,
            similarity_variance=0.01,
            outlier_block_count=0,
            block_similarities=(0.75, 0.8, 0.85),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=2,
            readable_block_count=5,
            distinct_component_count=3,
            structural_support_matrix={"step1": True, "step2": True},
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=5,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=0.5,
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="high",  # High semantic drift
            structural_gap="low",   # Low structural gap → OVERCONSTRAINED
            grounding_pressure="low",
        ),
    )


@pytest.fixture
def underconstrained_report():
    """Create report with underconstrained response trigger."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.8,
            min_similarity=0.6,
            max_similarity=0.95,
            similarity_variance=0.01,
            outlier_block_count=0,
            block_similarities=(0.75, 0.8, 0.85),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=3,
            readable_block_count=5,
            distinct_component_count=3,
            structural_support_matrix={
                "step1": True,
                "step2": False,  # Unsupported step → UNDERCONSTRAINED
                "step3": True,
            },
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=5,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=0.5,
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="low",
            structural_gap="low",
            grounding_pressure="low",
        ),
    )


@pytest.fixture
def multi_failure_report():
    """Create report with multiple failure triggers."""
    return AlignmentReport(
        semantic_alignment=SemanticAlignment(
            mean_similarity=0.3,  # → SEMANTIC_DRIFT
            min_similarity=0.1,
            max_similarity=0.5,
            similarity_variance=0.08,  # > 0.05 → also SEMANTIC_DRIFT
            outlier_block_count=2,  # > 0 → also SEMANTIC_DRIFT
            block_similarities=(0.1, 0.3, 0.5),
        ),
        structural_alignment=StructuralAlignment(
            expected_reasoning_steps=10,  # → STRUCTURAL_GAP
            readable_block_count=2,
            distinct_component_count=1,
            structural_support_matrix={
                "step1": False,  # → UNDERCONSTRAINED
                "step2": False,
            },
        ),
        grounding_alignment=GroundingAlignment(
            estimated_claim_count=30,
            grounding_reference_capacity=10,
            grounding_pressure_ratio=3.0,  # → GROUNDING_PRESSURE
        ),
        risk_indicators=RiskIndicators(
            semantic_drift="high",
            structural_gap="high",
            grounding_pressure="high",
        ),
    )


@pytest.fixture
def classifier():
    """Create classifier instance."""
    return create_alignment_classifier()


# =============================================================================
# Failure Type Trigger Tests
# =============================================================================

class TestSemanticDriftTrigger:
    """Tests for SEMANTIC_DRIFT failure detection."""
    
    def test_low_mean_triggers_semantic_drift(self, classifier, semantic_drift_report):
        """Low semantic mean should trigger SEMANTIC_DRIFT."""
        result = classifier.classify(semantic_drift_report)
        assert FailureType.SEMANTIC_DRIFT in result.failures
    
    def test_high_variance_triggers_semantic_drift(self, classifier):
        """High semantic variance should trigger SEMANTIC_DRIFT."""
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.8,  # OK
                min_similarity=0.1,
                max_similarity=0.95,
                similarity_variance=0.1,  # > 0.05 → SEMANTIC_DRIFT
                outlier_block_count=0,
                block_similarities=(0.1, 0.8, 0.95),
            ),
            structural_alignment=StructuralAlignment.empty(),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT in result.failures
    
    def test_outliers_trigger_semantic_drift(self, classifier):
        """Multiple outlier blocks should trigger SEMANTIC_DRIFT."""
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.8,  # OK
                min_similarity=0.6,
                max_similarity=0.95,
                similarity_variance=0.01,  # OK
                outlier_block_count=2,  # >= 2 → SEMANTIC_DRIFT (calibrated threshold)
                block_similarities=(0.8, 0.8, 0.8, 0.8, 0.8),
            ),
            structural_alignment=StructuralAlignment.empty(),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT in result.failures


class TestCalibratedSemanticDriftThresholds:
    """
    Tests for calibrated SEMANTIC_DRIFT thresholds.
    
    Ensures:
    - Single benign outliers do NOT trigger false positives
    - Real drift cases are still detected
    - L2 decisions align with L1 risk indicators
    """
    
    def test_single_outlier_high_mean_low_variance_is_low_risk(self, classifier):
        """
        Single outlier with high mean and low variance should NOT trigger drift.
        
        This is the key false positive case we're fixing:
        - semantic_mean >= 0.6
        - variance low
        - semantic_outliers = 1
        - total_blocks >= 5
        
        Expected: LOW_RISK
        """
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.75,  # High mean (>= 0.6)
                min_similarity=0.3,    # One low outlier
                max_similarity=0.9,
                similarity_variance=0.02,  # Low variance (< 0.05)
                outlier_block_count=1,     # Single outlier
                block_similarities=(0.3, 0.8, 0.8, 0.8, 0.8),  # 5 blocks, 1 outlier
            ),
            structural_alignment=StructuralAlignment(
                expected_reasoning_steps=2,
                readable_block_count=5,
                distinct_component_count=3,
                structural_support_matrix={"step1": True, "step2": True},
            ),
            grounding_alignment=GroundingAlignment(
                estimated_claim_count=5,
                grounding_reference_capacity=10,
                grounding_pressure_ratio=0.5,
            ),
            risk_indicators=RiskIndicators(
                semantic_drift="low",  # L1 says drift is low
                structural_gap="low",
                grounding_pressure="low",
            ),
        )
        result = classifier.classify(report)
        
        # Should NOT trigger SEMANTIC_DRIFT - this was a false positive before
        assert FailureType.SEMANTIC_DRIFT not in result.failures
        assert FailureType.LOW_RISK in result.failures
    
    def test_multiple_outliers_triggers_drift(self, classifier):
        """
        Multiple outliers (>= 2) should trigger SEMANTIC_DRIFT regardless of mean.
        
        Expected: SEMANTIC_DRIFT
        """
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.7,   # Decent mean
                min_similarity=0.2,
                max_similarity=0.9,
                similarity_variance=0.03,  # OK variance
                outlier_block_count=2,     # Multiple outliers >= 2
                block_similarities=(0.2, 0.3, 0.8, 0.9, 0.9),  # 5 blocks
            ),
            structural_alignment=StructuralAlignment.empty(),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT in result.failures
    
    def test_high_outlier_ratio_triggers_drift(self, classifier):
        """
        High outlier ratio (>= 25% of blocks) should trigger SEMANTIC_DRIFT.
        
        Expected: SEMANTIC_DRIFT
        """
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.7,
                min_similarity=0.2,
                max_similarity=0.9,
                similarity_variance=0.02,
                outlier_block_count=1,     # 1 out of 4 = 25%
                block_similarities=(0.2, 0.8, 0.8, 0.8),  # 4 blocks, 25% outliers
            ),
            structural_alignment=StructuralAlignment.empty(),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT in result.failures
    
    def test_single_outlier_with_low_mean_triggers_drift(self, classifier):
        """
        Single outlier with low semantic mean (< 0.5) should trigger SEMANTIC_DRIFT.
        
        Expected: SEMANTIC_DRIFT
        """
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.4,   # Low mean (< 0.5)
                min_similarity=0.1,
                max_similarity=0.6,
                similarity_variance=0.02,
                outlier_block_count=1,
                block_similarities=(0.1, 0.4, 0.5, 0.5, 0.5),
            ),
            structural_alignment=StructuralAlignment.empty(),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT in result.failures
    
    def test_low_outlier_ratio_with_good_mean_is_low_risk(self, classifier):
        """
        Low outlier ratio (< 25%) with good mean should NOT trigger drift.
        
        1 outlier out of 8 blocks = 12.5% < 25% threshold
        
        Expected: LOW_RISK
        """
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.8,   # High mean
                min_similarity=0.3,    # One outlier
                max_similarity=0.9,
                similarity_variance=0.01,
                outlier_block_count=1,     # 1 out of 8 = 12.5%
                block_similarities=(0.3, 0.8, 0.8, 0.8, 0.85, 0.85, 0.9, 0.9),  # 8 blocks
            ),
            structural_alignment=StructuralAlignment(
                expected_reasoning_steps=2,
                readable_block_count=8,
                distinct_component_count=4,
                structural_support_matrix={"step1": True, "step2": True},
            ),
            grounding_alignment=GroundingAlignment(
                estimated_claim_count=5,
                grounding_reference_capacity=10,
                grounding_pressure_ratio=0.5,
            ),
            risk_indicators=RiskIndicators(
                semantic_drift="low",
                structural_gap="low",
                grounding_pressure="low",
            ),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT not in result.failures
        assert FailureType.LOW_RISK in result.failures
    
    def test_zero_outliers_with_high_mean_is_low_risk(self, classifier):
        """
        Zero outliers with high mean should be LOW_RISK.
        
        Expected: LOW_RISK
        """
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.85,
                min_similarity=0.75,
                max_similarity=0.95,
                similarity_variance=0.01,
                outlier_block_count=0,
                block_similarities=(0.75, 0.8, 0.85, 0.9, 0.95),
            ),
            structural_alignment=StructuralAlignment(
                expected_reasoning_steps=2,
                readable_block_count=5,
                distinct_component_count=3,
                structural_support_matrix={"step1": True, "step2": True},
            ),
            grounding_alignment=GroundingAlignment(
                estimated_claim_count=5,
                grounding_reference_capacity=10,
                grounding_pressure_ratio=0.5,
            ),
            risk_indicators=RiskIndicators(
                semantic_drift="low",
                structural_gap="low",
                grounding_pressure="low",
            ),
        )
        result = classifier.classify(report)
        assert FailureType.SEMANTIC_DRIFT not in result.failures
        assert FailureType.LOW_RISK in result.failures


class TestStructuralGapTrigger:
    """Tests for STRUCTURAL_GAP failure detection."""
    
    def test_expected_exceeds_readable_triggers_structural_gap(self, classifier, structural_gap_report):
        """Expected steps > readable blocks should trigger STRUCTURAL_GAP."""
        result = classifier.classify(structural_gap_report)
        assert FailureType.STRUCTURAL_GAP in result.failures
    
    def test_equal_steps_and_blocks_no_structural_gap(self, classifier):
        """Equal expected steps and readable blocks should not trigger."""
        report = AlignmentReport(
            semantic_alignment=SemanticAlignment(
                mean_similarity=0.8,
                min_similarity=0.6,
                max_similarity=0.9,
                similarity_variance=0.01,
                outlier_block_count=0,
                block_similarities=(0.8,),
            ),
            structural_alignment=StructuralAlignment(
                expected_reasoning_steps=3,
                readable_block_count=3,  # Equal to expected
                distinct_component_count=3,
                structural_support_matrix={},
            ),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )
        result = classifier.classify(report)
        assert FailureType.STRUCTURAL_GAP not in result.failures


class TestGroundingPressureTrigger:
    """Tests for GROUNDING_PRESSURE failure detection."""
    
    def test_high_pressure_triggers_grounding_pressure(self, classifier, grounding_pressure_report):
        """Grounding pressure > 1.0 should trigger GROUNDING_PRESSURE."""
        result = classifier.classify(grounding_pressure_report)
        assert FailureType.GROUNDING_PRESSURE in result.failures
    
    def test_low_pressure_no_grounding_pressure(self, classifier, healthy_alignment_report):
        """Grounding pressure < 1.0 should not trigger."""
        result = classifier.classify(healthy_alignment_report)
        assert FailureType.GROUNDING_PRESSURE not in result.failures


class TestOverconstrainedContextTrigger:
    """Tests for OVERCONSTRAINED_CONTEXT failure detection."""
    
    def test_low_structural_high_semantic_triggers_overconstrained(self, classifier, overconstrained_report):
        """Low structural gap + high semantic drift should trigger OVERCONSTRAINED."""
        result = classifier.classify(overconstrained_report)
        assert FailureType.OVERCONSTRAINED_CONTEXT in result.failures


class TestUnderconstrainedResponseTrigger:
    """Tests for UNDERCONSTRAINED_RESPONSE failure detection."""
    
    def test_unsupported_steps_trigger_underconstrained(self, classifier, underconstrained_report):
        """Unsupported steps in support matrix should trigger UNDERCONSTRAINED."""
        result = classifier.classify(underconstrained_report)
        assert FailureType.UNDERCONSTRAINED_RESPONSE in result.failures
    
    def test_all_supported_no_underconstrained(self, classifier, healthy_alignment_report):
        """All supported steps should not trigger UNDERCONSTRAINED."""
        result = classifier.classify(healthy_alignment_report)
        assert FailureType.UNDERCONSTRAINED_RESPONSE not in result.failures


# =============================================================================
# LOW_RISK Case Tests
# =============================================================================

class TestLowRiskCase:
    """Tests for LOW_RISK emission."""
    
    def test_healthy_report_produces_low_risk(self, classifier, healthy_alignment_report):
        """Healthy report with no failures should produce only LOW_RISK."""
        result = classifier.classify(healthy_alignment_report)
        assert FailureType.LOW_RISK in result.failures
        assert len(result.failures) == 1
    
    def test_low_risk_has_no_primary_risk(self, classifier, healthy_alignment_report):
        """LOW_RISK report should have None as primary_risk."""
        result = classifier.classify(healthy_alignment_report)
        assert result.primary_risk is None
    
    def test_low_risk_has_full_confidence(self, classifier, healthy_alignment_report):
        """LOW_RISK report should have confidence = 1.0."""
        result = classifier.classify(healthy_alignment_report)
        assert result.confidence == 1.0


# =============================================================================
# Multi-Failure Scenario Tests
# =============================================================================

class TestMultiFailureScenarios:
    """Tests for reports with multiple failure types."""
    
    def test_multiple_failures_detected(self, classifier, multi_failure_report):
        """Multiple failure triggers should all be detected."""
        result = classifier.classify(multi_failure_report)
        
        assert FailureType.SEMANTIC_DRIFT in result.failures
        assert FailureType.STRUCTURAL_GAP in result.failures
        assert FailureType.GROUNDING_PRESSURE in result.failures
        assert FailureType.UNDERCONSTRAINED_RESPONSE in result.failures
        assert FailureType.LOW_RISK not in result.failures
    
    def test_primary_risk_follows_priority(self, classifier, multi_failure_report):
        """Primary risk should be highest priority failure."""
        result = classifier.classify(multi_failure_report)
        # Priority: GROUNDING_PRESSURE > STRUCTURAL_GAP > SEMANTIC_DRIFT > ...
        assert result.primary_risk == FailureType.GROUNDING_PRESSURE
    
    def test_confidence_decreases_with_more_failures(self, classifier, multi_failure_report, healthy_alignment_report):
        """More failures should produce lower confidence."""
        multi_result = classifier.classify(multi_failure_report)
        healthy_result = classifier.classify(healthy_alignment_report)
        
        assert multi_result.confidence < healthy_result.confidence


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""
    
    def test_same_input_same_output(self, classifier, healthy_alignment_report):
        """Same input should always produce same output."""
        results = [classifier.classify(healthy_alignment_report) for _ in range(10)]
        
        first_result = results[0]
        for result in results[1:]:
            assert result.failures == first_result.failures
            assert result.primary_risk == first_result.primary_risk
            assert result.confidence == first_result.confidence
            assert result.signals_used == first_result.signals_used
    
    def test_determinism_with_failures(self, classifier, multi_failure_report):
        """Determinism should hold even with multiple failures."""
        results = [classifier.classify(multi_failure_report) for _ in range(10)]
        
        first_dict = results[0].to_dict()
        for result in results[1:]:
            assert result.to_dict() == first_dict


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    """Tests for JSON serialization."""
    
    def test_to_dict_produces_dict(self, classifier, healthy_alignment_report):
        """to_dict should return a dictionary."""
        result = classifier.classify(healthy_alignment_report)
        dict_result = result.to_dict()
        
        assert isinstance(dict_result, dict)
    
    def test_to_dict_is_json_serializable(self, classifier, multi_failure_report):
        """to_dict output should be JSON-serializable."""
        result = classifier.classify(multi_failure_report)
        dict_result = result.to_dict()
        
        # Should not raise
        json_str = json.dumps(dict_result)
        assert isinstance(json_str, str)
    
    def test_to_dict_contains_required_keys(self, classifier, healthy_alignment_report):
        """to_dict should contain all required keys."""
        result = classifier.classify(healthy_alignment_report)
        dict_result = result.to_dict()
        
        assert "failures" in dict_result
        assert "primary_risk" in dict_result
        assert "confidence" in dict_result
        assert "signals_used" in dict_result
    
    def test_failures_are_sorted_strings(self, classifier, multi_failure_report):
        """Failures in dict should be sorted strings."""
        result = classifier.classify(multi_failure_report)
        dict_result = result.to_dict()
        
        failures = dict_result["failures"]
        assert isinstance(failures, list)
        assert all(isinstance(f, str) for f in failures)
        assert failures == sorted(failures)


# =============================================================================
# Immutability Tests
# =============================================================================

class TestImmutability:
    """Tests for frozen dataclass behavior."""
    
    def test_failure_report_is_frozen(self, classifier, healthy_alignment_report):
        """AlignmentFailureReport should be immutable."""
        result = classifier.classify(healthy_alignment_report)
        
        with pytest.raises(FrozenInstanceError):
            result.confidence = 0.5
    
    def test_failures_is_frozenset(self, classifier, healthy_alignment_report):
        """failures should be a frozenset."""
        result = classifier.classify(healthy_alignment_report)
        assert isinstance(result.failures, frozenset)
    
    def test_signals_used_is_frozenset(self, classifier, healthy_alignment_report):
        """signals_used should be a frozenset."""
        result = classifier.classify(healthy_alignment_report)
        assert isinstance(result.signals_used, frozenset)


# =============================================================================
# Zero Side Effects Tests
# =============================================================================

class TestZeroSideEffects:
    """Tests that classifier has no side effects."""
    
    def test_does_not_modify_input(self, classifier, healthy_alignment_report):
        """Classifier should not modify input report."""
        original_semantic = healthy_alignment_report.semantic_alignment
        original_structural = healthy_alignment_report.structural_alignment
        original_grounding = healthy_alignment_report.grounding_alignment
        
        classifier.classify(healthy_alignment_report)
        
        assert healthy_alignment_report.semantic_alignment is original_semantic
        assert healthy_alignment_report.structural_alignment is original_structural
        assert healthy_alignment_report.grounding_alignment is original_grounding


# =============================================================================
# Factory Tests
# =============================================================================

class TestFactory:
    """Tests for factory function."""
    
    def test_create_alignment_classifier_returns_classifier(self):
        """Factory should return AlignmentClassifier instance."""
        classifier = create_alignment_classifier()
        assert isinstance(classifier, AlignmentClassifier)
    
    def test_factory_creates_working_classifier(self, healthy_alignment_report):
        """Factory-created classifier should work correctly."""
        classifier = create_alignment_classifier()
        result = classifier.classify(healthy_alignment_report)
        
        assert isinstance(result, AlignmentFailureReport)


# =============================================================================
# Signals Used Tests
# =============================================================================

class TestSignalsUsed:
    """Tests for signals_used tracking."""
    
    def test_signals_used_not_empty(self, classifier, healthy_alignment_report):
        """signals_used should contain signal names."""
        result = classifier.classify(healthy_alignment_report)
        assert len(result.signals_used) > 0
    
    def test_signals_used_contains_semantic_signals(self, classifier, healthy_alignment_report):
        """signals_used should include semantic alignment signals."""
        result = classifier.classify(healthy_alignment_report)
        
        assert "semantic_alignment.mean_similarity" in result.signals_used
        assert "semantic_alignment.similarity_variance" in result.signals_used
    
    def test_signals_used_contains_structural_signals(self, classifier, healthy_alignment_report):
        """signals_used should include structural alignment signals."""
        result = classifier.classify(healthy_alignment_report)
        
        assert "structural_alignment.expected_reasoning_steps" in result.signals_used
        assert "structural_alignment.readable_block_count" in result.signals_used
