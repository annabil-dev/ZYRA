import pytest
import torch
from ai.brain.attention import MultiHeadAttention
from ai.brain.rope import RotaryPositionalEmbedding
from ai.brain.feed_forward import SwiGLUFeedForward
from ai.brain.transformer_block import TransformerBlock

@pytest.fixture
def attention_config():
    return {
        "hidden_size": 32,
        "num_attention_heads": 4,
        "attention_dropout": 0.0,
        "bias": False,
        "intermediate_size": 128,
        "rms_norm_eps": 1e-5
    }

def test_attention_shape_and_gradient(attention_config):
    x = torch.randn(2, 10, 32, requires_grad=True)
    rope = RotaryPositionalEmbedding(dim=8, max_seq_len=20)
    attn = MultiHeadAttention(attention_config)
    
    out = attn(x, rope)
    
    # Output shape should match input (B, T, D)
    assert out.shape == (2, 10, 32)
    assert torch.isfinite(out).all()
    
    loss = out.sum()
    loss.backward()
    
    assert x.grad is not None
    assert attn.q_proj.weight.grad is not None

def test_attention_invalid_heads(attention_config):
    config = attention_config.copy()
    config["num_attention_heads"] = 3 # 32 % 3 != 0
    with pytest.raises(ValueError, match="divisible by num_heads"):
        MultiHeadAttention(config)

def test_swiglu_shape_and_gradient(attention_config):
    x = torch.randn(2, 10, 32, requires_grad=True)
    ffn = SwiGLUFeedForward(attention_config)
    
    out = ffn(x)
    assert out.shape == (2, 10, 32)
    
    loss = out.sum()
    loss.backward()
    assert ffn.w_gate.weight.grad is not None

def test_transformer_block(attention_config):
    x = torch.randn(2, 10, 32)
    rope = RotaryPositionalEmbedding(dim=8, max_seq_len=20)
    block = TransformerBlock(attention_config)
    
    out = block(x, rope)
    assert out.shape == (2, 10, 32)
