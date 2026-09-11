import pytest
import torch
from ai.brain.rope import RotaryPositionalEmbedding

def test_rope_shape_and_rotation():
    # Q and K shapes: (B, H, T, HeadDim)
    q = torch.randn(2, 4, 10, 16)
    k = torch.randn(2, 4, 10, 16)
    
    rope = RotaryPositionalEmbedding(dim=16, max_seq_len=20)
    q_rot, k_rot = rope(q, k)
    
    assert q_rot.shape == q.shape
    assert k_rot.shape == k.shape
    assert torch.isfinite(q_rot).all()

def test_rope_cache_growth():
    rope = RotaryPositionalEmbedding(dim=16, max_seq_len=10)
    
    # Sequence length 5 (fits in cache)
    q = torch.randn(2, 4, 5, 16)
    k = torch.randn(2, 4, 5, 16)
    rope(q, k)
    assert rope.seq_len_cached == 10
    
    # Sequence length 15 (exceeds cache, should trigger rebuild)
    q = torch.randn(2, 4, 15, 16)
    k = torch.randn(2, 4, 15, 16)
    rope(q, k)
    assert rope.seq_len_cached == 15

def test_rope_device_dtype_awareness():
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")
        
    rope = RotaryPositionalEmbedding(dim=16, max_seq_len=10)
    q = torch.randn(2, 4, 5, 16, device="cuda", dtype=torch.float16)
    k = torch.randn(2, 4, 5, 16, device="cuda", dtype=torch.float16)
    
    q_rot, k_rot = rope(q, k)
    
    assert q_rot.device.type == "cuda"
    assert q_rot.dtype == torch.float16
    assert rope.cos_cached.device.type == "cuda"
    assert rope.cos_cached.dtype == torch.float16
