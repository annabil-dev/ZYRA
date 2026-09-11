import pytest
import torch
from ai.brain.rms_norm import RMSNorm

def test_rms_norm_shape_and_finite():
    # Input shape: (B, T, D)
    x = torch.randn(2, 10, 32)
    norm = RMSNorm(32)
    out = norm(x)
    
    assert out.shape == (2, 10, 32)
    assert torch.isfinite(out).all()
    
def test_rms_norm_gradient():
    x = torch.randn(2, 10, 32, requires_grad=True)
    norm = RMSNorm(32)
    out = norm(x)
    loss = out.sum()
    loss.backward()
    
    assert x.grad is not None
    assert norm.weight.grad is not None

def test_rms_norm_mathematics():
    # Compare against standard PyTorch operations manually
    x = torch.randn(2, 10, 32)
    norm = RMSNorm(32, eps=1e-5)
    out = norm(x)
    
    # Manual
    variance = x.pow(2).mean(dim=-1, keepdim=True)
    expected = x * torch.rsqrt(variance + 1e-5)
    
    assert torch.allclose(out, expected, atol=1e-6)
