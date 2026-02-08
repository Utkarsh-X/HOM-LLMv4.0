"""Unit tests for entity-centric indexing (Plan A).

Tests cover:
- Confidence scoring
- Entity extraction
- Relation extraction
- Hierarchical chunking
- Schema versioning
"""

import pytest
from pathlib import Path

# Test imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from homllm.common.config import (
    EntityConfidenceConfig,
    HierarchicalChunkingConfig,
    IndexerConfig,
    StorageConfig,
)
from homllm.common.types import (
    EntityInfo,
    GranularityLevel,
    RelationInfo,
    RelationType,
    SymbolKind,
)
from homllm.indexer.confidence_scorer import (
    compute_entity_confidence,
    ConfidenceInputs,
    is_public_name,
    compute_docstring_hash,
)


class TestConfidenceScorer:
    """Tests for deterministic confidence scoring."""

    def test_compute_entity_confidence_all_bonuses(self):
        """Test maximum confidence with all bonuses."""
        config = EntityConfidenceConfig(
            public_name_bonus=0.3,
            docstring_bonus=0.4,
            exported_bonus=0.2,
            type_annotated_bonus=0.1,
            cap_at=1.0,
        )
        inputs = ConfidenceInputs(
            name="process_data",
            has_docstring=True,
            is_exported=True,
            has_type_annotation=True,
        )
        
        score = compute_entity_confidence(inputs, config)
        assert score == pytest.approx(1.0)  # All bonuses sum to 1.0, capped at 1.0

    def test_compute_entity_confidence_no_bonuses(self):
        """Test minimum confidence with no bonuses."""
        config = EntityConfidenceConfig()
        inputs = ConfidenceInputs(
            name="_private_func",  # Private name, no bonus
            has_docstring=False,
            is_exported=False,
            has_type_annotation=False,
        )
        
        score = compute_entity_confidence(inputs, config)
        assert score == 0.0

    def test_compute_entity_confidence_public_name_only(self):
        """Test confidence with only public name bonus."""
        config = EntityConfidenceConfig(public_name_bonus=0.3)
        inputs = ConfidenceInputs(
            name="public_function",
            has_docstring=False,
            is_exported=False,
            has_type_annotation=False,
        )
        
        score = compute_entity_confidence(inputs, config)
        assert score == 0.3

    def test_compute_entity_confidence_capped(self):
        """Test that score is capped at cap_at value."""
        config = EntityConfidenceConfig(
            public_name_bonus=0.5,
            docstring_bonus=0.5,
            exported_bonus=0.5,
            type_annotated_bonus=0.5,
            cap_at=0.8,
        )
        inputs = ConfidenceInputs(
            name="high_confidence",
            has_docstring=True,
            is_exported=True,
            has_type_annotation=True,
        )
        
        score = compute_entity_confidence(inputs, config)
        assert score == 0.8  # Capped

    def test_is_public_name_public(self):
        """Test public name detection."""
        assert is_public_name("my_function") is True
        assert is_public_name("MyClass") is True
        assert is_public_name("CONSTANT") is True

    def test_is_public_name_private(self):
        """Test private name detection."""
        assert is_public_name("_private") is False
        assert is_public_name("__dunder__") is False
        assert is_public_name("__really_private") is False

    def test_compute_docstring_hash_consistent(self):
        """Test that docstring hash is consistent."""
        docstring = "This is a test docstring."
        hash1 = compute_docstring_hash(docstring)
        hash2 = compute_docstring_hash(docstring)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA-256 truncated to 16 chars

    def test_compute_docstring_hash_different(self):
        """Test that different docstrings produce different hashes."""
        hash1 = compute_docstring_hash("Docstring one")
        hash2 = compute_docstring_hash("Docstring two")
        
        assert hash1 != hash2


class TestEntityTypes:
    """Tests for entity type definitions."""

    def test_symbol_kind_includes_new_types(self):
        """Test that SymbolKind has all new entity types."""
        assert SymbolKind.IMPORT.value == "import"
        assert SymbolKind.ALIAS.value == "alias"
        assert SymbolKind.CONFIG_CONSTANT.value == "config_constant"
        assert SymbolKind.TYPE_ALIAS.value == "type_alias"

    def test_relation_type_includes_all_types(self):
        """Test that RelationType has all relation types."""
        assert RelationType.CALLS.value == "calls"
        assert RelationType.DEFINES.value == "defines"
        assert RelationType.USES.value == "uses"
        assert RelationType.IMPORTS.value == "imports"
        assert RelationType.RESOLVES_TO.value == "resolves_to"
        assert RelationType.INHERITS.value == "inherits"
        assert RelationType.OVERRIDES.value == "overrides"
        assert RelationType.TYPE_ANNOTATES.value == "type_annotates"

    def test_granularity_level_has_all_levels(self):
        """Test that GranularityLevel has all levels."""
        assert GranularityLevel.FINE.value == "fine"
        assert GranularityLevel.MEDIUM.value == "medium"
        assert GranularityLevel.COARSE.value == "coarse"


class TestEntityInfo:
    """Tests for EntityInfo dataclass."""

    def test_entity_info_creation(self):
        """Test EntityInfo creation with all fields."""
        entity = EntityInfo(
            entity_id="test123",
            entity_type="function",
            name="my_function",
            file_path="/path/to/file.py",
            span_start=10,
            span_end=20,
            docstring_hash="abc123",
            granularity_level="fine",
            confidence_score=0.7,
            has_type_annotation=True,
            is_exported=True,
            parent_entity_id="parent123",
        )
        
        assert entity.entity_id == "test123"
        assert entity.entity_type == "function"
        assert entity.name == "my_function"
        assert entity.span_start == 10
        assert entity.span_end == 20
        assert entity.confidence_score == 0.7
        assert entity.has_type_annotation is True
        assert entity.is_exported is True

    def test_entity_info_optional_fields(self):
        """Test EntityInfo with optional fields as None."""
        entity = EntityInfo(
            entity_id="test456",
            entity_type="variable",
            name="my_var",
            file_path="/path/to/file.py",
            span_start=5,
            span_end=5,
        )
        
        assert entity.docstring_hash is None
        assert entity.parent_entity_id is None


class TestRelationInfo:
    """Tests for RelationInfo dataclass."""

    def test_relation_info_creation(self):
        """Test RelationInfo creation."""
        relation = RelationInfo(
            src_entity_id="func1",
            dst_entity_id="func2",
            relation_type="calls",
            extraction_source="call_expression",
        )
        
        assert relation.src_entity_id == "func1"
        assert relation.dst_entity_id == "func2"
        assert relation.relation_type == "calls"
        assert relation.extraction_source == "call_expression"


class TestConfig:
    """Tests for configuration dataclasses."""

    def test_entity_confidence_config_defaults(self):
        """Test EntityConfidenceConfig default values."""
        config = EntityConfidenceConfig()
        
        assert config.public_name_bonus == 0.3
        assert config.docstring_bonus == 0.4
        assert config.exported_bonus == 0.2
        assert config.type_annotated_bonus == 0.1
        assert config.cap_at == 1.0

    def test_hierarchical_chunking_config_defaults(self):
        """Test HierarchicalChunkingConfig default values."""
        config = HierarchicalChunkingConfig()
        
        assert config.enabled is True
        assert config.fine_enabled is True
        assert config.medium_enabled is True
        assert config.coarse_enabled is True

    def test_indexer_config_post_init(self):
        """Test IndexerConfig post_init creates nested configs."""
        storage = StorageConfig(
            duckdb_path=Path("/tmp/db.duckdb"),
            tantivy_path=Path("/tmp/tantivy"),
            lancedb_path=Path("/tmp/lancedb"),
            artifacts_path=Path("/tmp/artifacts"),
        )
        config = IndexerConfig(
            languages=["python"],
            ignore_patterns=[],
            chunk_max_lines=100,
            storage=storage,
        )
        
        # post_init should create nested configs
        assert config.entity_confidence is not None
        assert config.hierarchical_chunking is not None
        assert config.entity_centric_indexing_enabled is True
        assert config.type_alias_extraction_enabled is False


class TestSchemaVersioning:
    """Tests for schema versioning."""

    def test_schema_version_is_2_0(self):
        """Test that schema version is 2.0 for Plan A."""
        from homllm.indexer.storage import INDEX_SCHEMA_VERSION
        
        assert INDEX_SCHEMA_VERSION == "2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
