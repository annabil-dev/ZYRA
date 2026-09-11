import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Any, Optional

from .rope import RotaryPositionalEmbedding

class MultiHeadAttention(nn.Module):
    """
    Multi-Head Causal Self-Attention.
    Uses scaled dot-product attention with causal masking.
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.hidden_size = config.get("hidden_size", 512)
        self.num_heads = config.get("num_attention_heads", 8)
        self.head_dim = self.hidden_size // self.num_heads
        self.dropout = config.get("attention_dropout", 0.0)
        self.bias = config.get("bias", False)
        
        if self.head_dim * self.num_heads != self.hidden_size:
            raise ValueError(f"hidden_size ({self.hidden_size}) must be divisible by num_heads ({self.num_heads})")
            
        # Linear projections
        # We use separate linears for clarity, though combined QKV is slightly faster.
        # Combined is fine, let's use separate for clean RoPE application.
        self.q_proj = nn.Linear(self.hidden_size, self.hidden_size, bias=self.bias)
        self.k_proj = nn.Linear(self.hidden_size, self.hidden_size, bias=self.bias)
        self.v_proj = nn.Linear(self.hidden_size, self.hidden_size, bias=self.bias)
        self.o_proj = nn.Linear(self.hidden_size, self.hidden_size, bias=self.bias)
        
        self.attn_dropout = nn.Dropout(self.dropout)
        
    def forward(self, x: torch.Tensor, rope: RotaryPositionalEmbedding) -> torch.Tensor:
        """
        Forward pass.
        Args:
            x: (B, T, D)
            rope: RotaryPositionalEmbedding instance.
        """
        B, T, D = x.size()
        
        # 1. Projections
        q = self.q_proj(x) # (B, T, D)
        k = self.k_proj(x) # (B, T, D)
        v = self.v_proj(x) # (B, T, D)
        
        # 2. Reshape to (B, H, T, HeadDim)
        q = q.view(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        
        # 3. Apply RoPE to Query and Key
        q, k = rope(q, k)
        
        # 4. Scaled Dot-Product Attention
        # scores: (B, H, T, T)
        scores = torch.matmul(q, k.transpose(-2, -1)) / (self.head_dim ** 0.5)
        
        # 5. Causal Mask
        # We need a mask of shape (T, T) where upper triangle is -inf
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=x.device), diagonal=1)
        # Replace True with -inf
        # Numerical safe masking
        scores = scores.masked_fill(mask, float('-inf'))
        
        # 6. Softmax
        # fp32 is safer for softmax
        probs = F.softmax(scores, dim=-1, dtype=torch.float32).to(q.dtype)
        probs = self.attn_dropout(probs)
        
        # 7. Weighted Sum
        # out: (B, H, T, HeadDim)
        out = torch.matmul(probs, v)
        
        # 8. Merge Heads
        # transpose back to (B, T, H, HeadDim) -> (B, T, D)
        out = out.transpose(1, 2).contiguous().view(B, T, D)
        
        # 9. Output Projection
        return self.o_proj(out)
