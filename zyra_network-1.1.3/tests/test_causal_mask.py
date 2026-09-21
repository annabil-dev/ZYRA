import pytest
import torch
from ai.brain.transformer import MyAIDecoderTransformer

@pytest.fixture
def tiny_config():
    return {
        "context_length": 8,
        "hidden_size": 32,
        "num_layers": 2,
        "num_attention_heads": 4,
        "intermediate_size": 64,
        "tie_word_embeddings": False
    }

def test_future_token_isolation(tiny_config):
    """
    CRITICAL TEST: Ensures Causal Masking is working correctly.
    Future tokens MUST NOT affect past token representations.
    """
    model = MyAIDecoderTransformer(tiny_config, vocab_size=100)
    model.eval() # Disable dropout for deterministic output
    
    # Sequence A
    input_a = torch.tensor([[10, 20, 30, 40]], dtype=torch.long)
    
    # Sequence B (Diverges after position 1)
    input_b = torch.tensor([[10, 20, 99, 88]], dtype=torch.long)
    
    with torch.no_grad():
        logits_a = model(input_a)
        logits_b = model(input_b)
        
    # Past positions (0 and 1) MUST be absolutely identical
    past_logits_a = logits_a[:, 0:2, :]
    past_logits_b = logits_b[:, 0:2, :]
    
    # Use strict tolerance for absolute equivalence
    assert torch.allclose(past_logits_a, past_logits_b, atol=1e-7), "CAUSAL MASK FAILED! Past tokens are affected by future tokens."
    
    # Future positions (2 and 3) should be different because input changed
    assert not torch.allclose(logits_a[:, 2:4, :], logits_b[:, 2:4, :])
