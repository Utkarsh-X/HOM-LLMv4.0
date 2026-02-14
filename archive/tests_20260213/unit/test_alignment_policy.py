"""
Unit tests for Level-3 Alignment Policy Decision Layer.

Tests verify:
- Determinism (same input → same policy)
- Correct mapping per failure type
- NONE/LOW_RISK returns None
- JSON serialization
- Zero side effects
- Immutability
"""

import pytest
import json
from dataclasses import FrozenInstanceError

from homllm.alignment import (
    FailureType,
    AlignmentFailureReport,
)
from homllm.alignment.policy import (
    ResponsePolicy,
    PolicyDecision,
    AlignmentPolicyEngine,
    create_policy_engine,
)
from homllm.alignment.policy.policy_mapper import map_failure_to_policy


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def policy_engine():
    """Create policy engine instance."""
    return create_policy_engine()


@pytest.fixture
def semantic_drift_failure():
    """Create failure report with SEMANTIC_DRIFT as primary."""
    return AlignmentFailureReport(
        failures=frozenset({FailureType.SEMANTIC_DRIFT}),
        primary_risk=FailureType.SEMANTIC_DRIFT,
        confidence=0.85,
        signals_used=frozenset({"semantic_alignment.mean_similarity"}),
    )


@pytest.fixture
def structural_gap_failure():
    """Create failure report with STRUCTURAL_GAP as primary."""
    return AlignmentFailureReport(
        failures=frozenset({FailureType.STRUCTURAL_GAP}),
        primary_risk=FailureType.STRUCTURAL_GAP,
        confidence=0.80,
        signals_used=frozenset({"structural_alignment.expected_reasoning_steps"}),
    )


@pytest.fixture
def grounding_pressure_failure():
    """Create failure report with GROUNDING_PRESSURE as primary."""
    return AlignmentFailureReport(
        failures=frozenset({FailureType.GROUNDING_PRESSURE}),
        primary_risk=FailureType.GROUNDING_PRESSURE,
        confidence=0.90,
        signals_used=frozenset({"grounding_alignment.grounding_pressure_ratio"}),
    )


@pytest.fixture
def overconstrained_failure():
    """Create failure report with OVERCONSTRAINED_CONTEXT as primary."""
    return AlignmentFailureReport(
        failures=frozenset({FailureType.OVERCONSTRAINED_CONTEXT}),
        primary_risk=FailureType.OVERCONSTRAINED_CONTEXT,
        confidence=0.75,
        signals_used=frozenset({"risk_indicators.structural_gap"}),
    )


@pytest.fixture
def underconstrained_failure():
    """Create failure report with UNDERCONSTRAINED_RESPONSE as primary."""
    return AlignmentFailureReport(
        failures=frozenset({FailureType.UNDERCONSTRAINED_RESPONSE}),
        primary_risk=FailureType.UNDERCONSTRAINED_RESPONSE,
        confidence=0.70,
        signals_used=frozenset({"structural_alignment.structural_support_matrix"}),
    )


@pytest.fixture
def low_risk_report():
    """Create LOW_RISK failure report."""
    return AlignmentFailureReport(
        failures=frozenset({FailureType.LOW_RISK}),
        primary_risk=None,
        confidence=1.0,
        signals_used=frozenset({"semantic_alignment.mean_similarity"}),
    )


# =============================================================================
# Policy Mapping Tests
# =============================================================================

class TestPolicyMapping:
    """Tests for failure type to policy mapping."""
    
    def test_semantic_drift_policy(self):
        """SEMANTIC_DRIFT should map to emphasize_runtime + require_example."""
        policy = map_failure_to_policy(FailureType.SEMANTIC_DRIFT)
        
        assert policy.emphasize_runtime_behavior is True
        assert policy.require_integrated_example is True
        assert policy.suppress_structural_listing is False
        assert policy.enforce_grounded_claims is False
    
    def test_structural_gap_policy(self):
        """STRUCTURAL_GAP should map to suppress_structural_listing."""
        policy = map_failure_to_policy(FailureType.STRUCTURAL_GAP)
        
        assert policy.emphasize_runtime_behavior is False
        assert policy.require_integrated_example is False
        assert policy.suppress_structural_listing is True
        assert policy.enforce_grounded_claims is False
    
    def test_grounding_pressure_policy(self):
        """GROUNDING_PRESSURE should map to enforce_grounded_claims."""
        policy = map_failure_to_policy(FailureType.GROUNDING_PRESSURE)
        
        assert policy.emphasize_runtime_behavior is False
        assert policy.require_integrated_example is False
        assert policy.suppress_structural_listing is False
        assert policy.enforce_grounded_claims is True
    
    def test_overconstrained_policy(self):
        """OVERCONSTRAINED_CONTEXT should map to emphasize_runtime + suppress_listing."""
        policy = map_failure_to_policy(FailureType.OVERCONSTRAINED_CONTEXT)
        
        assert policy.emphasize_runtime_behavior is True
        assert policy.require_integrated_example is False
        assert policy.suppress_structural_listing is True
        assert policy.enforce_grounded_claims is False
    
    def test_underconstrained_policy(self):
        """UNDERCONSTRAINED_RESPONSE should map to require_example."""
        policy = map_failure_to_policy(FailureType.UNDERCONSTRAINED_RESPONSE)
        
        assert policy.emphasize_runtime_behavior is False
        assert policy.require_integrated_example is True
        assert policy.suppress_structural_listing is False
        assert policy.enforce_grounded_claims is False
    
    def test_low_risk_policy(self):
        """LOW_RISK should map to all flags False."""
        policy = map_failure_to_policy(FailureType.LOW_RISK)
        
        assert policy.emphasize_runtime_behavior is False
        assert policy.require_integrated_example is False
        assert policy.suppress_structural_listing is False
        assert policy.enforce_grounded_claims is False


# =============================================================================
# Policy Engine Tests
# =============================================================================

class TestPolicyEngine:
    """Tests for policy engine decisions."""
    
    def test_low_risk_returns_none(self, policy_engine, low_risk_report):
        """LOW_RISK should return None (no policy needed)."""
        decision = policy_engine.decide(low_risk_report)
        assert decision is None
    
    def test_semantic_drift_returns_decision(self, policy_engine, semantic_drift_failure):
        """SEMANTIC_DRIFT should return a valid decision."""
        decision = policy_engine.decide(semantic_drift_failure)
        
        assert decision is not None
        assert decision.triggering_failure == FailureType.SEMANTIC_DRIFT
        assert decision.policy.emphasize_runtime_behavior is True
    
    def test_confidence_propagated(self, policy_engine, grounding_pressure_failure):
        """Confidence from L2 should propagate to decision."""
        decision = policy_engine.decide(grounding_pressure_failure)
        
        assert decision is not None
        assert decision.confidence == 0.90


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""
    
    def test_same_input_same_output(self, policy_engine, semantic_drift_failure):
        """Same input should produce same policy."""
        decisions = [policy_engine.decide(semantic_drift_failure) for _ in range(10)]
        
        first = decisions[0]
        for decision in decisions[1:]:
            assert decision.triggering_failure == first.triggering_failure
            assert decision.confidence == first.confidence
            assert decision.policy.to_dict() == first.policy.to_dict()
    
    def test_mapping_is_deterministic(self):
        """Mapping should be deterministic across calls."""
        policies = [map_failure_to_policy(FailureType.SEMANTIC_DRIFT) for _ in range(10)]
        
        first = policies[0]
        for policy in policies[1:]:
            assert policy.to_dict() == first.to_dict()


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    """Tests for JSON serialization."""
    
    def test_policy_to_dict(self):
        """ResponsePolicy should serialize correctly."""
        policy = ResponsePolicy(
            emphasize_runtime_behavior=True,
            require_integrated_example=True,
            suppress_structural_listing=False,
            enforce_grounded_claims=False,
            policy_confidence=0.85,
        )
        result = policy.to_dict()
        
        assert isinstance(result, dict)
        assert result["emphasize_runtime_behavior"] is True
        assert result["policy_confidence"] == 0.85
    
    def test_decision_to_dict(self, policy_engine, semantic_drift_failure):
        """PolicyDecision should serialize correctly."""
        decision = policy_engine.decide(semantic_drift_failure)
        result = decision.to_dict()
        
        assert isinstance(result, dict)
        assert "policy" in result
        assert "triggering_failure" in result
        assert "confidence" in result
        assert "active_flags" in result
    
    def test_serialization_is_json_compatible(self, policy_engine, semantic_drift_failure):
        """Serialized decision should be JSON-compatible."""
        decision = policy_engine.decide(semantic_drift_failure)
        result = decision.to_dict()
        
        # Should not raise
        json_str = json.dumps(result)
        assert isinstance(json_str, str)


# =============================================================================
# Active Flags Tests
# =============================================================================

class TestActiveFlags:
    """Tests for active_flags method."""
    
    def test_semantic_drift_flags(self):
        """SEMANTIC_DRIFT should produce EMPHASIZE_RUNTIME and REQUIRE_EXAMPLE."""
        policy = map_failure_to_policy(FailureType.SEMANTIC_DRIFT)
        flags = policy.active_flags()
        
        assert "EMPHASIZE_RUNTIME" in flags
        assert "REQUIRE_EXAMPLE" in flags
        assert len(flags) == 2
    
    def test_low_risk_no_flags(self):
        """LOW_RISK should produce no active flags."""
        policy = map_failure_to_policy(FailureType.LOW_RISK)
        flags = policy.active_flags()
        
        assert flags == []


# =============================================================================
# Immutability Tests
# =============================================================================

class TestImmutability:
    """Tests for frozen dataclass behavior."""
    
    def test_policy_is_frozen(self):
        """ResponsePolicy should be immutable."""
        policy = ResponsePolicy.none_policy()
        
        with pytest.raises(FrozenInstanceError):
            policy.emphasize_runtime_behavior = True
    
    def test_decision_is_frozen(self, policy_engine, semantic_drift_failure):
        """PolicyDecision should be immutable."""
        decision = policy_engine.decide(semantic_drift_failure)
        
        with pytest.raises(FrozenInstanceError):
            decision.confidence = 0.5


# =============================================================================
# Zero Side Effects Tests
# =============================================================================

class TestZeroSideEffects:
    """Tests that policy engine has no side effects."""
    
    def test_does_not_modify_input(self, policy_engine, semantic_drift_failure):
        """Policy engine should not modify input report."""
        original_failures = semantic_drift_failure.failures
        original_confidence = semantic_drift_failure.confidence
        
        policy_engine.decide(semantic_drift_failure)
        
        assert semantic_drift_failure.failures is original_failures
        assert semantic_drift_failure.confidence == original_confidence


# =============================================================================
# Factory Tests
# =============================================================================

class TestFactory:
    """Tests for factory function."""
    
    def test_create_policy_engine_returns_engine(self):
        """Factory should return AlignmentPolicyEngine instance."""
        engine = create_policy_engine()
        assert isinstance(engine, AlignmentPolicyEngine)
