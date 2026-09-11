import torch
import torch.nn as nn
from typing import Dict, Any

from .rms_norm import RMSNorm
from .attention import MultiHeadAttention
from .feed_forward import SwiGLUFeedForward
from .rope import RotaryPositionalEmbedding

class TransformerBlock(nn.Module):
    """
    A single Pre-Norm Transformer Block.
    x = x + Attention(RMSNorm(x))
    x = x + FFN(RMSNorm(x))
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.hidden_size = config.get("hidden_size", 512)
        self.eps = config.get("rms_norm_eps", 1e-5)
        
        self.attention_norm = RMSNorm(self.hidden_size, eps=self.eps)
        self.attention = MultiHeadAttention(config)
        
        self.ffn_norm = RMSNorm(self.hidden_size, eps=self.eps)
        self.feed_forward = SwiGLUFeedForward(config)
        
    def forward(self, x: torch.Tensor, rope: RotaryPositionalEmbedding) -> torch.Tensor:
        # Attention with residual
        norm_x = self.attention_norm(x)
        attn_out = self.attention(norm_x, rope)
        x = x + attn_out
        
        # FFN with residual
        norm_x = self.ffn_norm(x)
        ffn_out = self.feed_forward(norm_x)
        x = x + ffn_out
        
        return x
