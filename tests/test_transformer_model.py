import pytest
import torch
from ai.brain.transformer import MyAIDecoderTransformer

@pytest.fixture
def config():
    return {
        "context_length": 8,
        "hidden_size": 32,
        "num_layers": 2,
        "num_attention_heads": 4,
        "intermediate_size": 64,
        "tie_word_embeddings": False
    }

def test_transformer_model_shape_and_grad(config):
    model = MyAIDecoderTransformer(config, vocab_size=100)
    
    # Input (B, T)
    x = torch.randint(0, 100, (2, 5))
    
    # Forward
    logits = model(x)
    
    # Expected output (B, T, V)
    assert logits.shape == (2, 5, 100)
    assert torch.isfinite(logits).all()
    
    # Check parameters and gradient
    params = model.get_parameter_count()
    assert params["total_parameters"] > 0
    assert params["trainable_parameters"] == params["total_parameters"]
    
    loss = logits.sum()
    loss.backward()
    
    assert model.token_embedding.weight.grad is not None
    assert model.lm_head.weight.grad is not None
    assert model.blocks[0].attention.q_proj.weight.grad is not None
    
def test_transformer_context_validation(config):
    model = MyAIDecoderTransformer(config, vocab_size=100)
    
    # Input with T=10, exceeds context_length=8
    x = torch.randint(0, 100, (2, 10))
    
    with pytest.raises(ValueError, match="exceeds model context length"):
        model(x)
