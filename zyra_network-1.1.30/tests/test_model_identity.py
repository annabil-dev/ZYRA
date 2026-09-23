import pytest
import os
import json
from ai.models.metadata import ModelIdentity, ArchitectureMeta, TrainingLineage, ModelCard
from ai.models.registry import ModelRegistry

def test_model_identity():
    identity = ModelIdentity(
        project="MY-AI",
        family="ZYRA",
        generation="ZYRA-1",
        variant="Base",
        version="0.1.0-dev",
        status="development"
    )
    assert identity.display_name == "ZYRA-1 Base v0.1.0-dev"
    
def test_metadata_serialization(tmp_path):
    card = ModelCard(
        model=ModelIdentity(),
        architecture=ArchitectureMeta(),
        training=TrainingLineage(run_id="run_test", total_tokens_seen=1024),
        parameter_count=35000000
    )
    
    file_path = str(tmp_path / "model_card.yaml")
    card.save(file_path)
    
    assert os.path.exists(file_path)
    
    loaded = ModelCard.load(file_path)
    assert loaded.model.family == "ZYRA"
    assert loaded.training.total_tokens_seen == 1024
    assert loaded.parameter_count == 35000000
    
def test_model_registry(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    
    card = ModelCard(
        model=ModelIdentity(version="0.1.0-dev", status="development"),
        architecture=ArchitectureMeta(),
        training=TrainingLineage(),
        parameter_count=1000
    )
    
    registry.register_model(card, str(tmp_path / "model_v0.1.0"))
    
    # Should automatically set 'development' alias
    dev_path = registry.resolve_alias("development")
    assert dev_path == str(tmp_path / "model_v0.1.0")
    
    # Missing alias
    assert registry.resolve_alias("stable") is None
    
    models = registry.list_models()
    assert len(models) == 1
