import pytest
import torch
import torch.nn as nn
from ai.brain.baseline_mlp import FixedContextMLP
from ai.training.reproducibility import set_seed

@pytest.fixture
def model_config():
    return {
        "context_length": 8,
        "embedding_dim": 32,
        "hidden_dim": 64,
        "dropout": 0.0
    }

@pytest.fixture
def baseline_model(model_config):
    set_seed(42)
    return FixedContextMLP(model_config, vocab_size=100)

def test_model_construction_and_params(baseline_model):
    params = baseline_model.get_parameter_count()
    assert params["total_parameters"] > 0
    assert params["trainable_parameters"] == params["total_parameters"]
    assert isinstance(baseline_model, nn.Module)

def test_forward_pass_shapes(baseline_model):
    # Shape: (Batch=2, T=8)
    X = torch.randint(0, 100, (2, 8))
    
    logits = baseline_model(X)
    
    # Expected: (Batch=2, Vocab=100)
    assert logits.shape == (2, 100)
    
    # Ensure no NaN
    assert not torch.isnan(logits).any()

def test_invalid_input_shape(baseline_model):
    # T = 10, context_length = 8
    X = torch.randint(0, 100, (2, 10))
    with pytest.raises(ValueError, match="exceeds context length"):
        baseline_model(X)
        
    # T = 4, context_length = 8
    X = torch.randint(0, 100, (2, 4))
    with pytest.raises(ValueError, match="requires exactly"):
        baseline_model(X)
