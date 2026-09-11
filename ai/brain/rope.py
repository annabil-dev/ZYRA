import torch
import torch.nn as nn
from typing import Tuple

class RotaryPositionalEmbedding(nn.Module):
    """
    Rotary Positional Embedding (RoPE).
    Applies rotary embeddings to Query and Key matrices.
    """
    def __init__(self, dim: int, max_seq_len: int = 4096, base: float = 10000.0):
        super().__init__()
        self.dim = dim
        self.max_seq_len = max_seq_len
        self.base = base
        
        # Compute inverse frequencies
        # theta_i = 10000^(-2(i-1)/d) for i in [1, 2, ..., d/2]
        inv_freq = 1.0 / (base ** (torch.arange(0, dim, 2, dtype=torch.float32) / dim))
        self.register_buffer("inv_freq", inv_freq, persistent=False)
        
        self._build_cache(max_seq_len)
        
    def _build_cache(self, seq_len: int, device: torch.device = None, dtype: torch.dtype = None):
        """Builds and caches the sin and cos values."""
        t = torch.arange(seq_len, device=self.inv_freq.device, dtype=self.inv_freq.dtype)
        # Outer product: (seq_len, 1) x (1, dim/2) -> (seq_len, dim/2)
        freqs = torch.outer(t, self.inv_freq)
        
        # We need (seq_len, dim), typically duplicate freqs to match embedding dim
        # [theta_0, theta_1, ..., theta_{d/2-1}, theta_0, theta_1, ..., theta_{d/2-1}]
        emb = torch.cat((freqs, freqs), dim=-1)
        
        # Ensure it's on the right device and dtype if provided
        if device is not None or dtype is not None:
            emb = emb.to(device=device, dtype=dtype)
            
        self.register_buffer("cos_cached", emb.cos()[None, None, :, :], persistent=False)
        self.register_buffer("sin_cached", emb.sin()[None, None, :, :], persistent=False)
        self.seq_len_cached = seq_len
        
    def _rotate_half(self, x: torch.Tensor) -> torch.Tensor:
        """Rotates half the hidden dims of the input."""
        # x: (B, H, T, D)
        # Split D into two halves
        x1, x2 = x.chunk(2, dim=-1)
        # [-x2, x1]
        return torch.cat((-x2, x1), dim=-1)
        
    def forward(self, q: torch.Tensor, k: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Applies RoPE to q and k.
        Shapes:
            q: (B, H, T, D)
            k: (B, H, T, D)
        """
        seq_len = q.size(2)
        
        # Rebuild cache if sequence length exceeds cached length
        if seq_len > self.seq_len_cached:
            self._build_cache(seq_len, device=q.device, dtype=q.dtype)
        elif self.cos_cached.device != q.device or self.cos_cached.dtype != q.dtype:
            # Rebuild if device/dtype mismatch
            self._build_cache(self.seq_len_cached, device=q.device, dtype=q.dtype)
            
        # Slice cache to current sequence length
        cos = self.cos_cached[:, :, :seq_len, :]
        sin = self.sin_cached[:, :, :seq_len, :]
        
        # Apply rotation
        q_rot = (q * cos) + (self._rotate_half(q) * sin)
        k_rot = (k * cos) + (self._rotate_half(k) * sin)
        
        return q_rot, k_rot
