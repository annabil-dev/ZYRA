import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Any

class SwiGLUFeedForward(nn.Module):
    """
    SwiGLU Feed Forward Network.
    Formula: output = W_down(SiLU(W_gate(x)) * W_up(x))
    """
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.hidden_size = config.get("hidden_size", 512)
        self.intermediate_size = config.get("intermediate_size", 1536)
        self.bias = config.get("bias", False)
        
        self.w_gate = nn.Linear(self.hidden_size, self.intermediate_size, bias=self.bias)
        self.w_up = nn.Linear(self.hidden_size, self.intermediate_size, bias=self.bias)
        self.w_down = nn.Linear(self.intermediate_size, self.hidden_size, bias=self.bias)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Gate and Up projection
        gate = F.silu(self.w_gate(x))
        up = self.w_up(x)
        
        # Hadamard product
        hidden = gate * up
        
        # Down projection
        return self.w_down(hidden)
